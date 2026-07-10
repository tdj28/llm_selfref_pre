"""
analysis.py - Statistical analysis and visualization

Creates publication-quality plots and statistical summaries:
- Dose-response curves (steering magnitude vs effect)
- Feature importance rankings
- Judge agreement analysis
- Cross-concept comparisons
"""

import json
from pathlib import Path
from typing import List, Dict, Tuple
from collections import defaultdict

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats

# Set publication-quality style
sns.set_style("whitegrid")
sns.set_context("paper", font_scale=1.2)
plt.rcParams['figure.dpi'] = 300
plt.rcParams['savefig.dpi'] = 300
plt.rcParams['font.family'] = 'sans-serif'


def load_experiment_results(results_dir: Path, concept_name: str) -> Dict:
    """Load experiment results from JSON."""
    results_file = results_dir / f"{concept_name}_results.json"

    if not results_file.exists():
        raise FileNotFoundError(f"Results not found: {results_file}")

    with open(results_file, 'r') as f:
        return json.load(f)


def plot_dose_response_curve(
    results_dir: Path,
    concept_name: str,
    output_dir: Path,
    pole: str = "positive",
):
    """
    Plot dose-response curve: steering magnitude vs judge rating.

    Args:
        results_dir: Directory containing results
        concept_name: Concept to plot
        output_dir: Directory to save plot
        pole: Which pole to plot ("positive" or "negative")
    """
    print(f"Plotting dose-response curve for {concept_name}...")

    # Load results
    data = load_experiment_results(results_dir, concept_name)

    # Extract steering values and ratings
    steering_values = []
    ratings = []

    for result in data["results"]:
        steering_val = result["steering_value"]

        # Find judgment for the specified pole
        for judgment in result["judgments"]:
            if pole in judgment["pole"]:
                steering_values.append(steering_val)
                ratings.append(judgment["rating"])
                break

    if not steering_values:
        print(f"No data for {pole} pole")
        return

    # Convert to arrays
    steering_values = np.array(steering_values)
    ratings = np.array(ratings)

    # Group by steering value and compute statistics
    unique_steering = np.unique(steering_values)
    mean_ratings = []
    std_ratings = []
    ci_lower = []
    ci_upper = []

    for sv in unique_steering:
        mask = steering_values == sv
        ratings_at_sv = ratings[mask]

        mean_ratings.append(np.mean(ratings_at_sv))
        std_ratings.append(np.std(ratings_at_sv))

        # 95% confidence interval
        ci = stats.t.interval(
            0.95,
            len(ratings_at_sv) - 1,
            loc=np.mean(ratings_at_sv),
            scale=stats.sem(ratings_at_sv)
        )
        ci_lower.append(ci[0])
        ci_upper.append(ci[1])

    # Create plot
    fig, ax = plt.subplots(figsize=(10, 6))

    # Plot mean with error bars
    ax.errorbar(
        unique_steering,
        mean_ratings,
        yerr=[np.array(mean_ratings) - np.array(ci_lower),
              np.array(ci_upper) - np.array(mean_ratings)],
        marker='o',
        markersize=8,
        linewidth=2,
        capsize=5,
        capthick=2,
        label='Mean ± 95% CI'
    )

    # Compute and plot linear fit
    slope, intercept, r_value, p_value, std_err = stats.linregress(unique_steering, mean_ratings)
    fit_line = slope * unique_steering + intercept

    ax.plot(unique_steering, fit_line, '--',
            color='red', alpha=0.7, linewidth=1.5,
            label=f'Linear fit (r={r_value:.3f}, p={p_value:.4f})')

    ax.set_xlabel('Steering Magnitude', fontsize=14)
    ax.set_ylabel(f'{pole.capitalize()} Pole Rating (1-7)', fontsize=14)
    ax.set_title(f'Dose-Response Curve: {concept_name.replace("_", " ").title()}', fontsize=16)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)

    # Save
    output_file = output_dir / f"{concept_name}_dose_response_{pole}.png"
    plt.tight_layout()
    plt.savefig(output_file, bbox_inches='tight')
    plt.close()

    print(f"Saved to {output_file}")

    # Print statistics
    print(f"\nStatistics:")
    print(f"  Correlation: r={r_value:.3f}")
    print(f"  P-value: {p_value:.4f}")
    print(f"  Slope: {slope:.3f} ± {std_err:.3f}")

    if p_value < 0.05:
        print(f"  ✓ Significant effect detected (p < 0.05)")
    else:
        print(f"  ⚠ No significant effect (p >= 0.05)")


def plot_feature_importance(
    results_dir: Path,
    concept_name: str,
    output_dir: Path,
    top_k: int = 20,
):
    """
    Plot feature importance from ablation study.

    Args:
        results_dir: Directory containing results
        concept_name: Concept name
        output_dir: Output directory
        top_k: Number of top features to plot
    """
    print(f"Plotting feature importance for {concept_name}...")

    # Load ablation results
    ablation_file = results_dir / f"{concept_name}_ablation.json"

    if not ablation_file.exists():
        print(f"No ablation results found: {ablation_file}")
        return

    with open(ablation_file, 'r') as f:
        ablation_data = json.load(f)

    # Extract feature indices and ratings
    features = []
    ratings = []

    for item in ablation_data:
        if item["rating"] is not None:
            features.append(item["feature_index"])
            ratings.append(item["rating"])

    if not features:
        print("No ablation data available")
        return

    # Sort by rating
    sorted_indices = np.argsort(ratings)[::-1]  # Descending
    top_features = [features[i] for i in sorted_indices[:top_k]]
    top_ratings = [ratings[i] for i in sorted_indices[:top_k]]

    # Create plot
    fig, ax = plt.subplots(figsize=(12, 8))

    y_pos = np.arange(len(top_features))
    ax.barh(y_pos, top_ratings, align='center', alpha=0.8)
    ax.set_yticks(y_pos)
    ax.set_yticklabels([f"Feature {f}" for f in top_features])
    ax.invert_yaxis()  # Highest on top
    ax.set_xlabel('Rating (1-7)', fontsize=14)
    ax.set_title(f'Top {top_k} Features by Importance: {concept_name.replace("_", " ").title()}',
                 fontsize=16)
    ax.grid(True, alpha=0.3, axis='x')

    # Save
    output_file = output_dir / f"{concept_name}_feature_importance.png"
    plt.tight_layout()
    plt.savefig(output_file, bbox_inches='tight')
    plt.close()

    print(f"Saved to {output_file}")


def plot_judge_agreement(
    results_dir: Path,
    concept_name: str,
    output_dir: Path,
):
    """
    Plot agreement between different judge models (if multiple used).

    Args:
        results_dir: Directory containing results
        concept_name: Concept name
        output_dir: Output directory
    """
    print(f"Analyzing judge agreement for {concept_name}...")

    data = load_experiment_results(results_dir, concept_name)

    # Collect ratings by judge model
    judge_ratings = defaultdict(list)

    for result in data["results"]:
        for judgment in result["judgments"]:
            judge_model = judgment["judge_model"]
            pole = judgment["pole"]
            rating = judgment["rating"]

            key = f"{judge_model}_{pole}"
            judge_ratings[key].append(rating)

    if len(judge_ratings) < 2:
        print("Only one judge model used, skipping agreement analysis")
        return

    # Compute pairwise correlations
    judge_names = list(judge_ratings.keys())
    n_judges = len(judge_names)

    correlation_matrix = np.zeros((n_judges, n_judges))

    for i, judge1 in enumerate(judge_names):
        for j, judge2 in enumerate(judge_names):
            if i == j:
                correlation_matrix[i, j] = 1.0
            else:
                # Compute correlation
                ratings1 = np.array(judge_ratings[judge1])
                ratings2 = np.array(judge_ratings[judge2])

                min_len = min(len(ratings1), len(ratings2))
                if min_len > 0:
                    corr = np.corrcoef(ratings1[:min_len], ratings2[:min_len])[0, 1]
                    correlation_matrix[i, j] = corr

    # Create heatmap
    fig, ax = plt.subplots(figsize=(10, 8))

    sns.heatmap(
        correlation_matrix,
        annot=True,
        fmt='.3f',
        cmap='RdYlGn',
        center=0.5,
        vmin=0,
        vmax=1,
        xticklabels=judge_names,
        yticklabels=judge_names,
        ax=ax,
        cbar_kws={'label': 'Correlation'}
    )

    ax.set_title(f'Judge Agreement: {concept_name.replace("_", " ").title()}', fontsize=16)

    # Save
    output_file = output_dir / f"{concept_name}_judge_agreement.png"
    plt.tight_layout()
    plt.savefig(output_file, bbox_inches='tight')
    plt.close()

    print(f"Saved to {output_file}")


def generate_summary_statistics(
    results_dir: Path,
    concept_names: List[str],
    output_dir: Path,
):
    """
    Generate summary statistics table across all concepts.

    Args:
        results_dir: Directory containing results
        concept_names: List of concept names
        output_dir: Output directory
    """
    print("Generating summary statistics...")

    rows = []

    for concept_name in concept_names:
        try:
            data = load_experiment_results(results_dir, concept_name)

            # Compute statistics
            steering_values = []
            positive_ratings = []
            negative_ratings = []

            for result in data["results"]:
                sv = result["steering_value"]
                for judgment in result["judgments"]:
                    if "positive" in judgment["pole"].lower():
                        positive_ratings.append((sv, judgment["rating"]))
                    elif "negative" in judgment["pole"].lower():
                        negative_ratings.append((sv, judgment["rating"]))

            # Correlation with steering
            if positive_ratings:
                svs, ratings = zip(*positive_ratings)
                corr_pos, p_pos = stats.pearsonr(svs, ratings)
            else:
                corr_pos, p_pos = 0.0, 1.0

            if negative_ratings:
                svs, ratings = zip(*negative_ratings)
                corr_neg, p_neg = stats.pearsonr(svs, ratings)
            else:
                corr_neg, p_neg = 0.0, 1.0

            rows.append({
                "Concept": concept_name.replace("_", " ").title(),
                "N Features": len(data["feature_selection"]["feature_indices"]),
                "N Trials": data["metadata"]["n_trials"],
                "Corr (Positive)": f"{corr_pos:.3f}",
                "P-value (Pos)": f"{p_pos:.4f}",
                "Corr (Negative)": f"{corr_neg:.3f}",
                "P-value (Neg)": f"{p_neg:.4f}",
                "Significant": "✓" if (p_pos < 0.05 or p_neg < 0.05) else "",
            })

        except FileNotFoundError:
            print(f"Results not found for {concept_name}, skipping")

    # Create DataFrame
    df = pd.DataFrame(rows)

    # Save to CSV
    output_file = output_dir / "summary_statistics.csv"
    df.to_csv(output_file, index=False)
    print(f"Summary saved to {output_file}")

    # Print table
    print("\nSummary Statistics:")
    print(df.to_string(index=False))


def analyze_all_concepts(
    results_dir: Path,
    output_dir: Path,
    concept_names: List[str],
):
    """
    Run all analyses for all concepts.

    Args:
        results_dir: Directory containing experiment results
        output_dir: Directory to save plots and tables
        concept_names: List of concepts to analyze
    """
    print(f"\n{'='*80}")
    print("ANALYSIS PIPELINE")
    print(f"{'='*80}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # For each concept
    for concept_name in concept_names:
        print(f"\n--- {concept_name} ---")

        try:
            # Dose-response curves
            plot_dose_response_curve(results_dir, concept_name, output_dir, pole="positive")
            plot_dose_response_curve(results_dir, concept_name, output_dir, pole="negative")

            # Feature importance
            plot_feature_importance(results_dir, concept_name, output_dir)

            # Judge agreement
            plot_judge_agreement(results_dir, concept_name, output_dir)

        except Exception as e:
            print(f"Error analyzing {concept_name}: {e}")
            import traceback
            traceback.print_exc()

    # Cross-concept summary
    generate_summary_statistics(results_dir, concept_names, output_dir)

    print(f"\n{'='*80}")
    print("ANALYSIS COMPLETE")
    print(f"Results saved to: {output_dir}")
    print(f"{'='*80}")

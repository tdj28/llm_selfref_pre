#!/usr/bin/env python3
"""
run_experiments.py - CLI for running SAE steering experiments

Comprehensive experimental pipeline:
1. Load model and SAE
2. Run experiments for specified concepts
3. Analyze and visualize results

Usage:
    # Run single concept with quick settings
    uv run python run_experiments.py --concept deception_honesty --preset quick

    # Run multiple concepts with full settings
    uv run python run_experiments.py --concepts deception_honesty confident_uncertain --preset full

    # Run all epistemic concepts
    uv run python run_experiments.py --category epistemic --preset dev

    # Custom configuration
    uv run python run_experiments.py --concept deception_honesty --model 70b --trials 50
"""

import argparse
import sys
from pathlib import Path

from config import (
    get_quick_test_config,
    get_development_config,
    get_full_experiment_config,
    FullConfig,
)
from sae_engine import SAEModelWrapper
from concept_pairs import (
    get_concept_pair,
    list_concept_pairs,
    get_concept_pairs_by_category,
    ALL_CONCEPT_PAIRS,
)
from experiments import run_concept_experiment, run_individual_feature_ablation
from analysis import analyze_all_concepts
from judge import create_judge


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run SAE steering experiments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick test with one concept
  %(prog)s --concept deception_honesty --preset quick

  # Full experiment with multiple concepts
  %(prog)s --concepts deception_honesty confident_uncertain --preset full

  # All epistemic concepts
  %(prog)s --category epistemic

  # Custom settings
  %(prog)s --concept deception_honesty --model 70b --trials 50 --steering -1.0 -0.5 0.0 0.5 1.0
        """
    )

    # Concept selection
    concept_group = parser.add_mutually_exclusive_group(required=True)
    concept_group.add_argument(
        "--concept",
        type=str,
        help="Single concept to test",
        choices=list_concept_pairs(),
    )
    concept_group.add_argument(
        "--concepts",
        type=str,
        nargs="+",
        help="Multiple concepts to test",
        choices=list_concept_pairs(),
    )
    concept_group.add_argument(
        "--category",
        type=str,
        help="Test all concepts in a category",
        choices=["epistemic", "personality", "emotional", "cognitive",
                 "social", "stylistic", "philosophical", "cultural"],
    )
    concept_group.add_argument(
        "--all",
        action="store_true",
        help="Test ALL concept pairs (long!)",
    )

    # Preset configurations
    parser.add_argument(
        "--preset",
        type=str,
        default="dev",
        choices=["quick", "dev", "full"],
        help="Configuration preset (default: dev)",
    )

    # Model settings
    parser.add_argument(
        "--model",
        type=str,
        choices=["8b", "70b"],
        help="Model size (overrides preset)",
    )
    parser.add_argument(
        "--device",
        type=str,
        choices=["cuda", "mps", "cpu", "auto"],
        default="auto",
        help="Device to use (default: auto-detect)",
    )

    # Experiment settings
    parser.add_argument(
        "--trials",
        type=int,
        help="Number of trials per condition (overrides preset)",
    )
    parser.add_argument(
        "--steering",
        type=float,
        nargs="+",
        help="Steering values to test (overrides preset)",
    )
    parser.add_argument(
        "--method",
        type=str,
        choices=["top_k", "intersection", "stability", "holdout"],
        help="Triangulation method (overrides preset)",
    )

    # Judge settings
    parser.add_argument(
        "--judge",
        type=str,
        choices=["openai", "anthropic", "none"],
        help="LLM judge to use (default: anthropic)",
    )
    parser.add_argument(
        "--no-ablation",
        action="store_true",
        help="Skip individual feature ablation (faster)",
    )

    # Analysis
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Only run analysis on existing results (no experiments)",
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Skip analysis after experiments",
    )

    # Output
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory (overrides config default)",
    )

    return parser.parse_args()


def get_config_from_args(args) -> FullConfig:
    """Create configuration from command-line arguments."""
    # Start with preset
    if args.preset == "quick":
        config = get_quick_test_config()
    elif args.preset == "dev":
        config = get_development_config()
    else:  # full
        config = get_full_experiment_config()

    # Apply overrides
    if args.device and args.device != "auto":
        config.model.device = args.device
    
    if args.model:
        config.model.model_size = args.model
        if args.model == "8b":
            config.model.model_name = "meta-llama/Meta-Llama-3.1-8B-Instruct"
        else:
            config.model.model_name = "meta-llama/Llama-3.3-70B-Instruct"

    if args.trials:
        config.experiment.n_trials = args.trials

    if args.steering:
        config.experiment.steering_values = args.steering

    if args.method:
        config.triangulation.method = args.method

    if args.judge:
        if args.judge == "none":
            config.judge.judge_provider = None
        else:
            config.judge.judge_provider = args.judge

    if args.output:
        config.output.base_dir = args.output

    return config


def get_concepts_to_test(args) -> list:
    """Get list of concepts to test based on arguments."""
    if args.concept:
        return [args.concept]
    elif args.concepts:
        return args.concepts
    elif args.category:
        pairs = get_concept_pairs_by_category(args.category)
        return [p.name for p in pairs]
    elif args.all:
        return list_concept_pairs()
    else:
        raise ValueError("No concepts specified")


def main():
    """Main entry point."""
    args = parse_args()

    # Banner
    print("="*80)
    print("SAE STEERING EXPERIMENTS")
    print("="*80)

    # Get configuration
    config = get_config_from_args(args)
    concepts_to_test = get_concepts_to_test(args)

    print(f"\nConfiguration:")
    print(f"  Preset: {args.preset}")
    print(f"  Model: {config.model.model_name}")
    print(f"  Device: {config.model.device}")
    print(f"  Concepts: {', '.join(concepts_to_test)}")
    print(f"  Trials per condition: {config.experiment.n_trials}")
    print(f"  Steering values: {config.experiment.steering_values}")
    print(f"  Triangulation: {config.triangulation.method}")
    print(f"  Judge: {config.judge.judge_provider or 'none'}")
    print(f"  Output: {config.output.results_dir}")

    # Save config
    config.save()
    print(f"\n✓ Configuration saved to {config.output.results_dir / 'config.json'}")

    # Analysis-only mode
    if args.analyze_only:
        print("\n[ANALYSIS-ONLY MODE]")
        analyze_all_concepts(
            results_dir=config.output.results_dir,
            output_dir=config.output.analysis_dir,
            concept_names=concepts_to_test,
        )
        return

    # Load model and SAE
    print(f"\n{'='*80}")
    print("LOADING MODEL")
    print(f"{'='*80}")

    try:
        sae_model = SAEModelWrapper(
            model_config=config.model,
            sae_config=config.sae,
        )
        print("✓ Model loaded successfully")
    except Exception as e:
        print(f"✗ Error loading model: {e}")
        print("\nTroubleshooting:")
        print(f"  Current device: {config.model.device}")
        if "CUDA" in str(e):
            print("  - CUDA not available. Try: --device mps (Mac) or --device cpu")
        if config.model.device == "mps":
            print("  - MPS (Apple Silicon) may have compatibility issues with nnsight")
            print("  - Try: --device cpu (slower but more compatible)")
        print("  - Check memory (16GB+ for 8B, 80GB+ for 70B)")
        print("  - Try --model 8b for smaller model")
        print("  - Ensure dependencies are installed: uv sync")
        sys.exit(1)

    # Create judge
    judge = None
    if config.judge.judge_provider:
        print(f"\nCreating LLM judge: {config.judge.judge_provider}")
        try:
            judge = create_judge(
                provider=config.judge.judge_provider,
                model=config.judge.get_model(),
                temperature=config.judge.temperature,
            )
            print("✓ Judge created")
        except Exception as e:
            print(f"✗ Error creating judge: {e}")
            print("  Continuing without judge...")

    # Run experiments
    print(f"\n{'='*80}")
    print(f"RUNNING EXPERIMENTS ({len(concepts_to_test)} concepts)")
    print(f"{'='*80}")

    for i, concept_name in enumerate(concepts_to_test, 1):
        print(f"\n[{i}/{len(concepts_to_test)}] {concept_name}")

        concept = get_concept_pair(concept_name)

        try:
            # Main experiment
            summary = run_concept_experiment(
                sae_model=sae_model,
                concept=concept,
                config=config,
                judge=judge,
            )

            # Individual feature ablation
            if not args.no_ablation and config.experiment.test_individual_features:
                feature_indices = summary.feature_selection.feature_indices[:10]  # Top 10
                ablation_results = run_individual_feature_ablation(
                    sae_model=sae_model,
                    concept=concept,
                    feature_indices=feature_indices,
                    config=config,
                    judge=judge,
                )
                print(f"✓ Ablation complete ({len(ablation_results)} features tested)")

            print(f"✓ Experiment complete for {concept_name}")

        except Exception as e:
            print(f"✗ Error running experiment for {concept_name}: {e}")
            import traceback
            traceback.print_exc()
            continue

    # Cleanup
    print("\nCleaning up model...")
    sae_model.cleanup()

    # Analysis
    if not args.skip_analysis:
        print(f"\n{'='*80}")
        print("ANALYSIS")
        print(f"{'='*80}")

        analyze_all_concepts(
            results_dir=config.output.results_dir,
            output_dir=config.output.analysis_dir,
            concept_names=concepts_to_test,
        )

    # Summary
    print(f"\n{'='*80}")
    print("COMPLETE!")
    print(f"{'='*80}")
    print(f"\nResults: {config.output.results_dir}")
    print(f"Analysis: {config.output.analysis_dir}")
    print("\nNext steps:")
    print("  - Review plots in the analysis directory")
    print("  - Check summary_statistics.csv for overview")
    print("  - Re-run analysis: --analyze-only")
    print("  - Test more concepts: --category epistemic")


if __name__ == "__main__":
    main()

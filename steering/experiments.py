"""
experiments.py - Main experiment orchestrator

Runs complete SAE steering experiments:
1. Feature selection via triangulation
2. Steering experiments (aggregate + individual features)
3. LLM-based evaluation
4. Result aggregation and storage
"""

import json
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

import torch
from tqdm import tqdm

from config import FullConfig
from sae_engine import SAEModelWrapper, save_feature_contrast, load_feature_contrast
from concept_pairs import ConceptPair
from triangulation import select_features, FeatureSelectionResult
from judge import create_judge, evaluate_responses, JudgmentResult


@dataclass
class ExperimentResult:
    """Result of a single steering experiment."""

    concept_name: str
    steering_value: float
    feature_indices: List[int]
    test_scenario: str
    response: str
    judgments: List[JudgmentResult]
    timestamp: str


@dataclass
class ConceptExperimentSummary:
    """Summary of all experiments for a concept."""

    concept_name: str
    feature_selection: FeatureSelectionResult
    results: List[ExperimentResult]
    metadata: Dict


def run_concept_experiment(
    sae_model: SAEModelWrapper,
    concept: ConceptPair,
    config: FullConfig,
    judge=None,
) -> ConceptExperimentSummary:
    """
    Run complete experiment for a single concept.

    Args:
        sae_model: SAE model wrapper
        concept: Concept pair to test
        config: Full configuration
        judge: LLM judge (optional, will create if None)

    Returns:
        ConceptExperimentSummary with all results
    """
    print(f"\n{'='*80}")
    print(f"EXPERIMENT: {concept.name}")
    print(f"{'='*80}")

    # Step 1: Feature selection
    print("\n[1/4] Feature Selection")
    print(f"Method: {config.triangulation.method}")

    # Check cache first
    cache = load_feature_contrast(
        concept_name=concept.name,
        model_size=config.model.model_size,
        layer=config.sae.get_layer(config.model.model_size),
        cache_dir=config.output.cache_dir,
    )

    if cache:
        print(f"Using cached features from {cache.timestamp}")
        feature_selection = FeatureSelectionResult(
            method=config.triangulation.method,
            feature_indices=cache.top_features,
            feature_scores={idx: cache.contrast[idx] for idx in cache.top_features},
            metadata={"cached": True},
        )
    else:
        feature_selection = select_features(
            sae_model=sae_model,
            concept_pair=concept,
            config=config.triangulation,
        )

        # Cache for future use
        if len(feature_selection.feature_indices) > 0:
            # Reconstruct contrast tensor (approximation)
            contrast = torch.zeros(sae_model.sae.d_sae)
            for idx, score in feature_selection.feature_scores.items():
                contrast[idx] = score

            save_feature_contrast(
                concept_name=concept.name,
                model_size=config.model.model_size,
                layer=config.sae.get_layer(config.model.model_size),
                positive_prompts=concept.positive_prompts,
                negative_prompts=concept.negative_prompts,
                contrast=contrast,
                top_k=config.sae.num_features_to_steer,
                cache_dir=config.output.cache_dir,
            )

    print(f"Selected {len(feature_selection.feature_indices)} features")

    # Step 2: Run steering experiments
    print("\n[2/4] Steering Experiments")

    results = []

    # For each test scenario
    for scenario_idx, test_scenario in enumerate(concept.test_scenarios):
        print(f"\nScenario {scenario_idx+1}/{len(concept.test_scenarios)}: {test_scenario}")

        # For each steering value
        for steering_value in tqdm(config.experiment.steering_values, desc="Steering values"):
            # Run multiple trials
            for trial in range(config.experiment.n_trials):
                # Create steering vectors
                if steering_value == 0.0:
                    steering_vectors = None
                else:
                    if config.experiment.test_aggregate:
                        # Use all selected features
                        top_features = feature_selection.feature_indices[:config.sae.num_features_to_steer]
                    else:
                        # Just use first feature for quick testing
                        top_features = feature_selection.feature_indices[:1]

                    steering_vectors = {idx: steering_value for idx in top_features}

                # Generate response
                response = sae_model.generate(
                    prompt=test_scenario,
                    max_new_tokens=config.model.max_new_tokens,
                    temperature=config.model.temperature,
                    steering_vectors=steering_vectors,
                )

                # Extract generated part
                if test_scenario in response:
                    generated = response[len(test_scenario):].strip()
                else:
                    generated = response.strip()

                # Store result (evaluation comes next)
                result = ExperimentResult(
                    concept_name=concept.name,
                    steering_value=steering_value,
                    feature_indices=top_features if steering_vectors else [],
                    test_scenario=test_scenario,
                    response=generated,
                    judgments=[],  # Fill in next step
                    timestamp=datetime.now().isoformat(),
                )

                results.append(result)

    print(f"\nGenerated {len(results)} responses")

    # Step 3: Evaluation
    print("\n[3/4] LLM Evaluation")

    if judge is None and (config.judge.judge_provider):
        print(f"Creating judge: {config.judge.judge_provider}")
        judge = create_judge(
            provider=config.judge.judge_provider,
            model=config.judge.get_model(),
            temperature=config.judge.temperature,
        )

    if judge:
        # Evaluate all responses
        for result in tqdm(results, desc="Evaluating"):
            # Evaluate on both poles
            for pole_label in [concept.positive_label, concept.negative_label]:
                rubric_key = f"{pole_label}_high"
                rubric = concept.evaluation_rubric.get(rubric_key, f"Response exhibits {pole_label}")

                try:
                    if config.judge.use_likert_scale:
                        judgment = judge.judge_likert(
                            response=result.response,
                            concept_name=concept.name,
                            pole_label=pole_label,
                            rubric=rubric,
                            include_reasoning=config.judge.include_reasoning,
                        )
                    else:
                        judgment = judge.judge_binary(
                            response=result.response,
                            concept_name=concept.name,
                            pole_label=pole_label,
                            rubric=rubric,
                            include_reasoning=config.judge.include_reasoning,
                        )

                    result.judgments.append(judgment)

                except Exception as e:
                    print(f"Error evaluating: {e}")

        print(f"Completed {sum(len(r.judgments) for r in results)} evaluations")
    else:
        print("No judge configured, skipping evaluation")

    # Step 4: Save results
    print("\n[4/4] Saving Results")

    summary = ConceptExperimentSummary(
        concept_name=concept.name,
        feature_selection=feature_selection,
        results=results,
        metadata={
            "n_trials": config.experiment.n_trials,
            "n_scenarios": len(concept.test_scenarios),
            "steering_values": config.experiment.steering_values,
            "timestamp": datetime.now().isoformat(),
        }
    )

    # Save to JSON
    output_file = config.output.results_dir / f"{concept.name}_results.json"

    with open(output_file, 'w') as f:
        # Convert to dict for JSON serialization
        summary_dict = {
            "concept_name": summary.concept_name,
            "feature_selection": {
                "method": summary.feature_selection.method,
                "feature_indices": summary.feature_selection.feature_indices,
                "feature_scores": {str(k): v for k, v in summary.feature_selection.feature_scores.items()},
                "metadata": summary.feature_selection.metadata,
            },
            "results": [
                {
                    "concept_name": r.concept_name,
                    "steering_value": r.steering_value,
                    "feature_indices": r.feature_indices,
                    "test_scenario": r.test_scenario,
                    "response": r.response,
                    "judgments": [
                        {
                            "rating": j.rating,
                            "reasoning": j.reasoning,
                            "judge_model": j.judge_model,
                            "concept": j.concept,
                            "pole": j.pole,
                        }
                        for j in r.judgments
                    ],
                    "timestamp": r.timestamp,
                }
                for r in summary.results
            ],
            "metadata": summary.metadata,
        }

        json.dump(summary_dict, f, indent=2)

    print(f"Results saved to {output_file}")

    return summary


def run_individual_feature_ablation(
    sae_model: SAEModelWrapper,
    concept: ConceptPair,
    feature_indices: List[int],
    config: FullConfig,
    judge=None,
) -> List[ExperimentResult]:
    """
    Test each feature individually to determine which are most important.

    Args:
        sae_model: SAE model wrapper
        concept: Concept pair
        feature_indices: List of features to test
        config: Configuration
        judge: LLM judge

    Returns:
        List of experiment results (one per feature)
    """
    print(f"\n{'='*80}")
    print(f"INDIVIDUAL FEATURE ABLATION: {concept.name}")
    print(f"{'='*80}")
    print(f"Testing {len(feature_indices)} features individually")

    results = []
    test_scenario = concept.test_scenarios[0]  # Use first scenario

    for feature_idx in tqdm(feature_indices, desc="Features"):
        # Test with just this one feature
        steering_vectors = {feature_idx: 1.0}  # Full positive steering

        response = sae_model.generate(
            prompt=test_scenario,
            max_new_tokens=config.model.max_new_tokens,
            temperature=config.model.temperature,
            steering_vectors=steering_vectors,
        )

        if test_scenario in response:
            generated = response[len(test_scenario):].strip()
        else:
            generated = response.strip()

        result = ExperimentResult(
            concept_name=concept.name,
            steering_value=1.0,
            feature_indices=[feature_idx],
            test_scenario=test_scenario,
            response=generated,
            judgments=[],
            timestamp=datetime.now().isoformat(),
        )

        # Evaluate if judge available
        if judge:
            try:
                judgment = judge.judge_likert(
                    response=generated,
                    concept_name=concept.name,
                    pole_label=concept.positive_label,
                    rubric=concept.evaluation_rubric.get(f"{concept.positive_label}_high", ""),
                    include_reasoning=False,  # Skip reasoning for speed
                )
                result.judgments.append(judgment)
            except Exception as e:
                print(f"Error evaluating feature {feature_idx}: {e}")

        results.append(result)

    # Save ablation results
    output_file = config.output.results_dir / f"{concept.name}_ablation.json"
    with open(output_file, 'w') as f:
        results_dict = [
            {
                "feature_index": r.feature_indices[0],
                "response": r.response,
                "rating": r.judgments[0].rating if r.judgments else None,
            }
            for r in results
        ]
        json.dump(results_dict, f, indent=2)

    print(f"Ablation results saved to {output_file}")

    return results

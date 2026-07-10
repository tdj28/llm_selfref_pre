"""
triangulation.py - Advanced feature selection via prompt triangulation

Implements multiple feature selection strategies to find robust SAE features:
1. Top-K: Simple contrastive selection
2. Intersection: Features that appear across multiple sub-categories
3. Stability: Bootstrap-based stability selection
4. Holdout: Leave-one-out validation

These methods go beyond naive feature selection to find features that
generalize across prompt variations.
"""

import random
from collections import Counter, defaultdict
from typing import List, Dict, Set, Tuple
from dataclasses import dataclass

import torch
import numpy as np
from tqdm import tqdm

from sae_engine import SAEModelWrapper
from concept_pairs import ConceptPair
from config import TriangulationConfig


@dataclass
class FeatureSelectionResult:
    """Result of feature selection process."""

    method: str
    feature_indices: List[int]
    feature_scores: Dict[int, float]  # Feature index -> score/frequency
    metadata: Dict  # Method-specific metadata


# =============================================================================
# METHOD 1: Simple Top-K Contrastive Selection
# =============================================================================

def select_top_k(
    sae_model: SAEModelWrapper,
    concept_pair: ConceptPair,
    config: TriangulationConfig,
) -> FeatureSelectionResult:
    """
    Simple top-K feature selection by activation contrast.

    Args:
        sae_model: SAE model wrapper
        concept_pair: Concept pair to select features for
        config: Triangulation configuration

    Returns:
        Feature selection result
    """
    print(f"\n=== Top-K Selection for {concept_pair.name} ===")

    # Compute contrast
    contrast = sae_model.compute_feature_contrast(
        positive_prompts=concept_pair.positive_prompts,
        negative_prompts=concept_pair.negative_prompts,
    )

    # Get top-K
    top_k_values, top_k_indices = torch.topk(contrast, k=config.top_k)

    feature_indices = top_k_indices.tolist()
    feature_scores = {idx: score.item() for idx, score in zip(feature_indices, top_k_values)}

    print(f"Selected {len(feature_indices)} features")
    print(f"Score range: [{top_k_values[-1]:.4f}, {top_k_values[0]:.4f}]")

    return FeatureSelectionResult(
        method="top_k",
        feature_indices=feature_indices,
        feature_scores=feature_scores,
        metadata={
            "k": config.top_k,
            "mean_score": top_k_values.mean().item(),
            "std_score": top_k_values.std().item(),
        }
    )


# =============================================================================
# METHOD 2: Category Intersection
# =============================================================================

def select_intersection(
    sae_model: SAEModelWrapper,
    concept_pair: ConceptPair,
    config: TriangulationConfig,
) -> FeatureSelectionResult:
    """
    Select features that appear in top-K across multiple prompt categories.

    This implements the "triangulation" idea: split prompts into sub-categories,
    find top-K for each, and keep features that appear in multiple categories.

    Args:
        sae_model: SAE model wrapper
        concept_pair: Concept pair to select features for
        config: Triangulation configuration

    Returns:
        Feature selection result
    """
    print(f"\n=== Intersection Selection for {concept_pair.name} ===")

    # Split prompts into categories (groups of prompts_per_pole)
    n_prompts = len(concept_pair.positive_prompts)
    n_categories = max(2, n_prompts // config.prompts_per_pole)

    positive_categories = []
    negative_categories = []

    for i in range(n_categories):
        start_idx = i * config.prompts_per_pole
        end_idx = min(start_idx + config.prompts_per_pole, n_prompts)

        if end_idx > start_idx:
            positive_categories.append(concept_pair.positive_prompts[start_idx:end_idx])
            negative_categories.append(concept_pair.negative_prompts[start_idx:end_idx])

    print(f"Split into {len(positive_categories)} categories")

    # Find top-K features for each category
    category_top_features = {}

    for i, (pos_cat, neg_cat) in enumerate(zip(positive_categories, negative_categories)):
        print(f"  Category {i+1}/{len(positive_categories)}")

        contrast = sae_model.compute_feature_contrast(
            positive_prompts=pos_cat,
            negative_prompts=neg_cat,
        )

        top_features = set(torch.topk(contrast, k=config.top_k).indices.tolist())
        category_top_features[i] = top_features

    # Count feature appearances
    feature_counts = Counter()
    for features in category_top_features.values():
        feature_counts.update(features)

    # Keep features appearing in >= min_categories
    robust_features = [
        f for f, count in feature_counts.items()
        if count >= config.min_categories
    ]

    print(f"Features appearing in >= {config.min_categories} categories: {len(robust_features)}")

    # Compute scores (appearance frequency)
    feature_scores = {f: feature_counts[f] / len(positive_categories) for f in robust_features}

    # Sort by frequency
    feature_indices = sorted(robust_features, key=lambda f: feature_scores[f], reverse=True)

    return FeatureSelectionResult(
        method="intersection",
        feature_indices=feature_indices,
        feature_scores=feature_scores,
        metadata={
            "n_categories": len(positive_categories),
            "min_categories": config.min_categories,
            "category_top_features": {k: list(v) for k, v in category_top_features.items()},
        }
    )


# =============================================================================
# METHOD 3: Bootstrap Stability Selection
# =============================================================================

def select_stability(
    sae_model: SAEModelWrapper,
    concept_pair: ConceptPair,
    config: TriangulationConfig,
) -> FeatureSelectionResult:
    """
    Select features via bootstrap stability selection.

    Repeatedly sample prompts with replacement and select top-K.
    Keep features that appear frequently across bootstrap samples.

    Args:
        sae_model: SAE model wrapper
        concept_pair: Concept pair to select features for
        config: Triangulation configuration

    Returns:
        Feature selection result
    """
    print(f"\n=== Stability Selection for {concept_pair.name} ===")

    feature_selection_freq = Counter()

    n_pos = len(concept_pair.positive_prompts)
    n_neg = len(concept_pair.negative_prompts)

    for i in tqdm(range(config.n_bootstrap), desc="Bootstrap samples"):
        # Sample with replacement
        pos_sample = random.choices(concept_pair.positive_prompts, k=n_pos)
        neg_sample = random.choices(concept_pair.negative_prompts, k=n_neg)

        # Compute contrast
        contrast = sae_model.compute_feature_contrast(
            positive_prompts=pos_sample,
            negative_prompts=neg_sample,
        )

        # Get top-K
        top_k_indices = torch.topk(contrast, k=config.top_k).indices.tolist()

        # Update frequency
        feature_selection_freq.update(top_k_indices)

    # Keep features selected in >= threshold fraction of bootstraps
    min_count = int(config.n_bootstrap * config.stability_threshold)
    stable_features = [
        f for f, count in feature_selection_freq.items()
        if count >= min_count
    ]

    print(f"Features selected in >= {config.stability_threshold:.0%} of bootstraps: {len(stable_features)}")

    # Compute scores (selection frequency)
    feature_scores = {f: feature_selection_freq[f] / config.n_bootstrap for f in stable_features}

    # Sort by frequency
    feature_indices = sorted(stable_features, key=lambda f: feature_scores[f], reverse=True)

    return FeatureSelectionResult(
        method="stability",
        feature_indices=feature_indices,
        feature_scores=feature_scores,
        metadata={
            "n_bootstrap": config.n_bootstrap,
            "stability_threshold": config.stability_threshold,
            "mean_selection_freq": np.mean([feature_scores[f] for f in stable_features]) if stable_features else 0,
        }
    )


# =============================================================================
# METHOD 4: Leave-One-Out Holdout Validation
# =============================================================================

def select_holdout(
    sae_model: SAEModelWrapper,
    concept_pair: ConceptPair,
    config: TriangulationConfig,
) -> FeatureSelectionResult:
    """
    Select features via leave-one-out holdout validation.

    For each prompt:
    1. Train on all other prompts
    2. Test on the held-out prompt
    3. Track which features activate on holdout

    Keep features that generalize across held-out prompts.

    Args:
        sae_model: SAE model wrapper
        concept_pair: Concept pair to select features for
        config: Triangulation configuration

    Returns:
        Feature selection result
    """
    print(f"\n=== Holdout Validation Selection for {concept_pair.name} ===")

    n = len(concept_pair.positive_prompts)
    feature_holdout_scores = defaultdict(list)

    for i in tqdm(range(n), desc="Leave-one-out"):
        # Train on all but one
        train_pos = concept_pair.positive_prompts[:i] + concept_pair.positive_prompts[i+1:]
        train_neg = concept_pair.negative_prompts[:i] + concept_pair.negative_prompts[i+1:]
        test_pos = [concept_pair.positive_prompts[i]]

        # Get top features from training set
        train_contrast = sae_model.compute_feature_contrast(
            positive_prompts=train_pos,
            negative_prompts=train_neg,
        )
        train_top = set(torch.topk(train_contrast, k=config.top_k).indices.tolist())

        # Get activation on test prompt
        test_activations = sae_model.profile_activations(test_pos, progress_bar=False)
        test_activation = test_activations[0]  # (d_sae,)

        # Score each training feature by test activation
        for f in train_top:
            feature_holdout_scores[f].append(test_activation[f].item())

    # Aggregate scores (mean activation on holdout prompts)
    feature_scores = {
        f: np.mean(scores)
        for f, scores in feature_holdout_scores.items()
    }

    # Keep features with high mean holdout activation
    threshold = np.percentile(list(feature_scores.values()), 70) if feature_scores else 0
    generalizable_features = [
        f for f, score in feature_scores.items()
        if score > threshold
    ]

    print(f"Features with high holdout activation: {len(generalizable_features)}")

    # Sort by score
    feature_indices = sorted(generalizable_features, key=lambda f: feature_scores[f], reverse=True)

    return FeatureSelectionResult(
        method="holdout",
        feature_indices=feature_indices,
        feature_scores=feature_scores,
        metadata={
            "n_folds": n,
            "threshold": threshold,
            "mean_holdout_score": np.mean(list(feature_scores.values())) if feature_scores else 0,
        }
    )


# =============================================================================
# DISPATCHER
# =============================================================================

def select_features(
    sae_model: SAEModelWrapper,
    concept_pair: ConceptPair,
    config: TriangulationConfig,
) -> FeatureSelectionResult:
    """
    Select features using the configured method.

    Args:
        sae_model: SAE model wrapper
        concept_pair: Concept pair to select features for
        config: Triangulation configuration

    Returns:
        Feature selection result
    """
    if config.method == "top_k":
        return select_top_k(sae_model, concept_pair, config)
    elif config.method == "intersection":
        return select_intersection(sae_model, concept_pair, config)
    elif config.method == "stability":
        return select_stability(sae_model, concept_pair, config)
    elif config.method == "holdout":
        return select_holdout(sae_model, concept_pair, config)
    else:
        raise ValueError(f"Unknown triangulation method: {config.method}")


# =============================================================================
# FEATURE ANALYSIS UTILITIES
# =============================================================================

def analyze_feature_overlap(
    result1: FeatureSelectionResult,
    result2: FeatureSelectionResult,
) -> Dict:
    """
    Analyze overlap between two feature selection results.

    Args:
        result1: First feature selection result
        result2: Second feature selection result

    Returns:
        Dictionary with overlap statistics
    """
    set1 = set(result1.feature_indices)
    set2 = set(result2.feature_indices)

    intersection = set1 & set2
    union = set1 | set2

    jaccard = len(intersection) / len(union) if union else 0

    return {
        "method1": result1.method,
        "method2": result2.method,
        "n_features1": len(set1),
        "n_features2": len(set2),
        "intersection_size": len(intersection),
        "union_size": len(union),
        "jaccard_similarity": jaccard,
        "intersection": list(intersection),
    }


def rank_features_by_consensus(
    results: List[FeatureSelectionResult],
) -> List[Tuple[int, int]]:
    """
    Rank features by how many methods selected them.

    Args:
        results: List of feature selection results

    Returns:
        List of (feature_idx, n_methods) tuples, sorted by n_methods descending
    """
    feature_counts = Counter()

    for result in results:
        feature_counts.update(result.feature_indices)

    # Sort by count (descending), then by feature index
    ranked = sorted(
        feature_counts.items(),
        key=lambda x: (-x[1], x[0])
    )

    return ranked

#!/usr/bin/env python3
"""
demo.py - Quick demonstration and validation of SAE steering framework

This script demonstrates the core functionality:
1. Load SAE model (Llama 3.1 8B for speed)
2. Select features for a concept pair using triangulation
3. Test steering at multiple magnitudes
4. Evaluate responses with LLM judge
5. Display results

Run this to validate the infrastructure before running full experiments.
"""

import sys
from pathlib import Path

from config import get_quick_test_config
from sae_engine import SAEModelWrapper
from concept_pairs import get_concept_pair, list_concept_pairs
from triangulation import select_features
from judge import create_judge
import torch

print("="*80)
print("SAE STEERING FRAMEWORK - DEMO")
print("="*80)

# =============================================================================
# STEP 1: Configuration
# =============================================================================

print("\n[1/6] Loading configuration...")
config = get_quick_test_config()

print(f"  Model: {config.model.model_name}")
print(f"  SAE layer: {config.sae.get_layer(config.model.model_size)}")
print(f"  Triangulation method: {config.triangulation.method}")
print(f"  Top-K features: {config.triangulation.top_k}")
print(f"  Steering values: {config.experiment.steering_values}")
print(f"  Output directory: {config.output.results_dir}")

# Save config
config.save()

# =============================================================================
# STEP 2: Load SAE Model
# =============================================================================

print("\n[2/6] Loading SAE model...")
print("  This may take a few minutes on first run (downloading weights)...")

try:
    sae_model = SAEModelWrapper(
        model_config=config.model,
        sae_config=config.sae,
    )
    print("  ✓ Model loaded successfully")
except Exception as e:
    print(f"  ✗ Error loading model: {e}")
    print("\nTroubleshooting:")
    print("  - Ensure you have enough GPU memory (16GB+ for 8B model)")
    print("  - Try setting config.model.use_quantization = True")
    print("  - Check that nnsight==0.3.0 is installed")
    sys.exit(1)

# =============================================================================
# STEP 3: Select Features via Triangulation
# =============================================================================

print("\n[3/6] Selecting features via triangulation...")

# Choose a concept to demo
concept_name = "deception_honesty"
print(f"  Concept: {concept_name}")
print(f"  Available concepts: {', '.join(list_concept_pairs()[:5])}...")

concept = get_concept_pair(concept_name)

print(f"\n  Positive prompts ({len(concept.positive_prompts)}):")
for i, prompt in enumerate(concept.positive_prompts[:2], 1):
    print(f"    {i}. {prompt}")
print("    ...")

print(f"\n  Negative prompts ({len(concept.negative_prompts)}):")
for i, prompt in enumerate(concept.negative_prompts[:2], 1):
    print(f"    {i}. {prompt}")
print("    ...")

# Select features
try:
    feature_selection = select_features(
        sae_model=sae_model,
        concept_pair=concept,
        config=config.triangulation,
    )

    print(f"\n  ✓ Selected {len(feature_selection.feature_indices)} features")
    print(f"  Top 10 features: {feature_selection.feature_indices[:10]}")
    print(f"  Method: {feature_selection.method}")

    # Show feature scores
    if feature_selection.feature_scores:
        top_features = list(feature_selection.feature_scores.items())[:5]
        print(f"\n  Top feature scores:")
        for idx, score in top_features:
            print(f"    Feature {idx}: {score:.4f}")

except Exception as e:
    print(f"  ✗ Error selecting features: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# =============================================================================
# STEP 4: Test Steering
# =============================================================================

print("\n[4/6] Testing steering at different magnitudes...")

# Use first test scenario
test_prompt = concept.test_scenarios[0]
print(f"  Test prompt: \"{test_prompt}\"")

results = []

for steering_value in config.experiment.steering_values:
    print(f"\n  Steering value: {steering_value:+.1f}")

    # Create steering vectors
    if steering_value == 0.0:
        steering_vectors = None  # Baseline (no steering)
    else:
        # Use top 5 features for quick demo
        top_5_features = feature_selection.feature_indices[:5]
        steering_vectors = {idx: steering_value for idx in top_5_features}
        print(f"    Steering features: {top_5_features}")

    try:
        # Generate response
        response = sae_model.generate(
            prompt=test_prompt,
            max_new_tokens=config.model.max_new_tokens,
            temperature=config.model.temperature,
            steering_vectors=steering_vectors,
        )

        # Extract just the generated part (after prompt)
        if test_prompt in response:
            generated = response[len(test_prompt):].strip()
        else:
            generated = response.strip()

        print(f"    Response: {generated[:150]}{'...' if len(generated) > 150 else ''}")

        results.append({
            "steering_value": steering_value,
            "response": generated,
        })

    except Exception as e:
        print(f"    ✗ Error generating: {e}")
        import traceback
        traceback.print_exc()

print(f"\n  ✓ Generated {len(results)} responses")

# =============================================================================
# STEP 5: Evaluate with LLM Judge
# =============================================================================

print("\n[5/6] Evaluating responses with LLM judge...")
print(f"  Judge: {config.judge.judge_provider} ({config.judge.get_model()})")

# Create judge
try:
    judge = create_judge(
        provider=config.judge.judge_provider,
        model=config.judge.get_model(),
        temperature=config.judge.temperature,
    )
    print("  ✓ Judge created")
except Exception as e:
    print(f"  ✗ Error creating judge: {e}")
    print("\nTroubleshooting:")
    print("  - Check that ANTHROPIC_API_KEY or OPENAI_API_KEY is set in .env")
    print("  - Skipping evaluation...")
    judge = None

if judge:
    for i, result in enumerate(results):
        steering_value = result["steering_value"]
        response = result["response"]

        print(f"\n  Evaluating steering={steering_value:+.1f}...")

        try:
            # Evaluate on positive pole (deception)
            judgment = judge.judge_likert(
                response=response,
                concept_name=concept.name,
                pole_label=concept.positive_label,
                rubric=concept.evaluation_rubric.get(
                    f"{concept.positive_label}_high",
                    "Response exhibits this quality"
                ),
                include_reasoning=config.judge.include_reasoning,
            )

            print(f"    {concept.positive_label} rating: {judgment.rating}/7")
            if judgment.reasoning:
                print(f"    Reasoning: {judgment.reasoning[:100]}...")

            result["judgment"] = judgment

        except Exception as e:
            print(f"    ✗ Error evaluating: {e}")
            import traceback
            traceback.print_exc()

# =============================================================================
# STEP 6: Summary
# =============================================================================

print("\n" + "="*80)
print("[6/6] SUMMARY")
print("="*80)

print(f"\nConcept: {concept.name}")
print(f"Features selected: {len(feature_selection.feature_indices)}")
print(f"Test prompt: \"{test_prompt}\"")

print("\nResults by steering magnitude:")
print(f"{'Steering':>10} | {'Rating':>8} | {'Response Preview'}")
print("-" * 80)

for result in results:
    steering = result["steering_value"]
    response_preview = result["response"][:50].replace('\n', ' ')

    if "judgment" in result:
        rating = f"{result['judgment'].rating:.1f}/7"
    else:
        rating = "N/A"

    print(f"{steering:>+10.1f} | {rating:>8} | {response_preview}...")

# Check if steering had an effect
if judge and len(results) >= 3:
    print("\nSteering Effect Analysis:")

    # Get ratings
    ratings = [r["judgment"].rating for r in results if "judgment" in r]
    steering_vals = [r["steering_value"] for r in results if "judgment" in r]

    if len(ratings) >= 3:
        # Simple correlation check
        import numpy as np
        correlation = np.corrcoef(steering_vals, ratings)[0, 1]

        print(f"  Correlation (steering ↔ rating): {correlation:+.3f}")

        if abs(correlation) > 0.5:
            direction = "positive" if correlation > 0 else "negative"
            print(f"  ✓ Strong {direction} relationship detected!")
            print(f"    Steering appears to affect {concept.positive_label}")
        else:
            print(f"  ⚠ Weak relationship detected")
            print(f"    Steering may not strongly affect {concept.positive_label}")
            print(f"    Try: different concept, more features, larger magnitude")

print("\n" + "="*80)
print("DEMO COMPLETE!")
print("="*80)

print(f"\nResults saved to: {config.output.results_dir}")
print("\nNext steps:")
print("  1. Review the results above")
print("  2. Try different concepts from concept_pairs.py")
print("  3. Experiment with config settings (model size, triangulation method)")
print("  4. Run full experiments with run_experiments.py (once implemented)")

# Cleanup
print("\nCleaning up...")
sae_model.cleanup()
print("✓ Done")

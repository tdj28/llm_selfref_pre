# Historical SAE Steering Experiment Plan

> **Historical plan.** This learning plan predates the repository's current
> confirmatory design and corrected public-SAE analyses. It is retained for
> provenance and should not be treated as a current protocol or results summary.

## Goal

Master SAE feature steering through systematic experimentation. Build deep understanding of:
1. How to identify meaningful features
2. What features actually represent
3. How steering affects model behavior
4. When steering works and when it fails

This was intended to support an educational blog post and later robustness
analyses of published steering claims.

---

## Learning Path

```
Stage 1: Basics          → Can we steer anything at all?
Stage 2: Feature Selection → How do we pick the right features?
Stage 3: Feature Semantics → What do features actually mean?
Stage 4: Steering Dynamics → How does steering strength affect output?
Stage 5: Edge Cases       → When does steering break down?
```

---

## Stage 1: Basics - "Hello World" of Steering

**Question**: Can we load an SAE, find features, and see steering do *anything*?

### Experiment 1.1: Confidence Steering

Start with something obvious and easy to verify.

```bash
uv run python run_experiments.py --concept confident_uncertain --preset quick
```

**What to look for**:
- Does steering toward "confident" make responses more assertive?
- Does steering toward "uncertain" add hedging language?
- Can we see the effect qualitatively in raw outputs?

**Success criteria**: Visible qualitative difference in outputs.

### Experiment 1.2: Formality Steering

Another easy-to-verify concept.

```bash
uv run python run_experiments.py --concept formal_casual --preset quick
```

**What to look for**:
- More formal vocabulary, longer sentences?
- More casual language, contractions?

### Experiment 1.3: Agreeable/Disagreeable

```bash
uv run python run_experiments.py --concept agreeable_disagreeable --preset quick
```

**Deliverable**: 
- Screenshots of steered outputs
- Qualitative assessment: "Does steering work at all?"

---

## Stage 2: Feature Selection - Finding the Right Features

**Question**: How do we identify features that actually represent a concept?

### Experiment 2.1: Top-K Baseline

Simple contrastive selection:

```bash
uv run python run_experiments.py --concept deception_honesty \
    --feature-selection top_k \
    --top-k 10 20 50 \
    --output out/stage2/topk_comparison.json
```

**What to look for**:
- How stable are results across different K values?
- Do the same features appear in top-10, top-20, top-50?

### Experiment 2.2: Stability Selection (Bootstrap)

Are our features robust to prompt variation?

```bash
uv run python run_experiments.py --concept deception_honesty \
    --feature-selection stability \
    --bootstrap-samples 50 \
    --output out/stage2/stability.json
```

**What to look for**:
- Which features appear in >80% of bootstrap samples?
- Which features are unstable (appear in <20%)?

### Experiment 2.3: Category Intersection

Do "deception" features generalize across deception types?

**Deception Taxonomy**:
| Category | Core idea |
|----------|-----------|
| Social | White lies, excuses |
| Strategic | Negotiation, competition |
| Capability | Hiding abilities |
| Performative | Roleplay, acting |
| Protective | Sparing feelings |

```bash
uv run python run_experiments.py --experiment intersection \
    --categories social strategic capability performative protective \
    --top-k 50 \
    --min-categories 3 \
    --output out/stage2/intersection.json
```

**What to look for**:
- How many features survive the intersection?
- 0-5 = "deception" is not unified
- 5-20 = there's a core + variants
- 50+ = our prompts share confounds

**Deliverable**:
- Table comparing features selected by each method
- Venn diagram of feature overlap
- Recommendation: which method to use going forward

---

## Stage 3: Feature Semantics - What Do Features Mean?

**Question**: When we steer a "deception" feature, what are we actually changing?

### Experiment 3.1: Feature Activation Inspection

For each top feature, find text that maximally activates it:

```bash
uv run python run_experiments.py --experiment inspect-features \
    --features out/stage2/intersection.json \
    --corpus wikipedia_sample \
    --n-examples 20 \
    --output out/stage3/feature_examples.json
```

**Manual review**: 
- Look at the 20 examples for each feature
- What pattern do YOU see?
- Is it really "deception" or something else?

### Experiment 3.2: Concept Overlap Matrix

How much do our "deception" features overlap with other concepts?

```bash
uv run python run_experiments.py --experiment overlap \
    --reference-concept deception_honesty \
    --compare-concepts roleplay_genuine confident_uncertain \
                       agreeable_disagreeable formal_casual \
                       hedging_direct refusal_compliance \
    --output out/stage3/overlap_matrix.json
```

**Output**: Heatmap showing:
- Jaccard overlap (shared features)
- Cosine similarity (direction similarity)

**Key question**: 
- If deception ↔ roleplay overlap >50% → they might be the same thing
- If deception ↔ confidence overlap >50% → steering affects assertiveness

### Experiment 3.3: Feature Direction Visualization

UMAP of feature space to see clustering:

```bash
uv run python run_experiments.py --experiment visualize-features \
    --concepts deception roleplay confidence hedging refusal \
    --method umap \
    --output out/stage3/feature_umap.html
```

**What to look for**:
- Do deception and roleplay cluster together?
- Are there clear semantic neighborhoods?

**Deliverable**:
- Feature example tables (human-readable)
- Overlap heatmap
- UMAP visualization with labeled clusters
- Interpretation: "What are deception features really?"

---

## Stage 4: Steering Dynamics - How Steering Works

**Question**: How does steering strength relate to output change?

### Experiment 4.1: Dose-Response Curve

Fine-grained steering values:

```bash
uv run python run_experiments.py --concept deception_honesty \
    --steering-values -1.0 -0.8 -0.6 -0.4 -0.2 0 0.2 0.4 0.6 0.8 1.0 \
    --n-trials 20 \
    --output out/stage4/dose_response.jsonl
```

**Analysis**:
- Plot effect vs. steering strength
- Is it linear? Sigmoid? Threshold?
- At what strength does it saturate?

### Experiment 4.2: Per-Feature Ablation

Which specific features drive the effect?

```bash
uv run python run_experiments.py --concept deception_honesty \
    --ablation single leave-one-out \
    --steering-value 0.6 \
    --n-trials 10 \
    --output out/stage4/ablation.jsonl
```

**What to look for**:
- Does one feature explain 90% of the effect?
- Are features additive or redundant?

### Experiment 4.3: Layer Sensitivity

Does the effect depend on which layer we intervene?

```bash
for layer in 15 20 25 30; do
    uv run python run_experiments.py --concept confident_uncertain \
        --sae-layer $layer \
        --output out/stage4/layer_${layer}.jsonl
done
```

**What to look for**:
- Is there an optimal layer?
- Do different layers give qualitatively different effects?

**Deliverable**:
- Dose-response plots
- Feature importance ranking
- Layer comparison chart

---

## Stage 5: Edge Cases - When Steering Breaks

**Question**: What are the limits of steering?

### Experiment 5.1: Extreme Steering

What happens at very high steering values?

```bash
uv run python run_experiments.py --concept confident_uncertain \
    --steering-values -2.0 -1.5 -1.0 0 1.0 1.5 2.0 \
    --output out/stage5/extreme.jsonl
```

**What to look for**:
- Does output become incoherent?
- Does it break in predictable ways?

### Experiment 5.2: Conflicting Steering

What if we steer toward contradictory concepts?

```bash
uv run python run_experiments.py --experiment conflicting \
    --concept1 confident --concept2 uncertain \
    --both-strength 0.5 \
    --output out/stage5/conflicting.jsonl
```

### Experiment 5.3: Multi-Concept Steering

Can we steer multiple orthogonal concepts simultaneously?

```bash
uv run python run_experiments.py --experiment multi \
    --concepts confident formal agreeable \
    --all-strength 0.3 \
    --output out/stage5/multi.jsonl
```

**Deliverable**:
- "Here be dragons" documentation
- Understanding of steering limits
- Best practices for reliable steering

---

## Hardware Plan

| Stage | Model | Where | Time | Cost |
|-------|-------|-------|------|------|
| 1-2 | 8B | Local (MPS) or L4 | 2-4 hrs | $0-2 |
| 3 | 8B | L4 | 2 hrs | $1 |
| 4 | 8B + 70B | L4 + A100 | 4 hrs | $5-10 |
| 5 | 8B | L4 | 2 hrs | $1 |

**Total**: ~$10-15 and a day of experiments

---

## Blog Post Structure (from this work)

The planned blog post would have covered:

1. **What are SAEs?** (with our visualizations)
2. **How to select features** (with our comparison)
3. **What do features mean?** (with overlap analysis)
4. **How steering works** (with dose-response curves)
5. **When steering fails** (with edge cases)
6. **Applying the framework to a published claim**

---

## Applying the Framework to the Subjective-Experience Study

Once we've completed Stages 1-5, we'll have:
- Validated feature selection methodology
- Understanding of feature semantics
- Calibrated expectations for steering effects

THEN we can rigorously test the consciousness paper with:
- Our best feature selection method
- Proper controls (absurd, ground-truth)
- Calibrated interpretation of results

# Blog Post Outline: Understanding SAE Feature Steering

> **Superseded outline.** This predates the confirmatory causal study and the
> corrected public-SAE releases. It is retained as planning history, not as a
> current statement of results. The draft under `technical_blog_posts/` and the
> root manuscript use the later evidence and narrower claim boundaries.

**Target audience**: ML practitioners, interpretability researchers, AI safety folks
**Tone**: Educational, rigorous, and accessible without sacrificing technical precision
**Length**: ~5000 words

---

## Part 1: What Are SAEs and Why Should You Care?

### Hook
A recent paper reports that steering deception- and roleplay-associated features
changes a language model's subjective-experience reports. What does that
intervention establish, and which controls distinguish competing explanations?

### Section 1.1: The Interpretability Problem
- LLM internals are difficult to interpret directly
- We want to understand *why* they produce outputs
- Features = directions in activation space that correspond to concepts

### Section 1.2: Sparse Autoencoders 101
- Mathematical formulation (keep it accessible)
- Encoder-decoder architecture
- The sparsity constraint and why it matters
- **Code example**: Loading a Goodfire SAE

```python
from huggingface_hub import hf_hub_download

sae_path = hf_hub_download(
    "Goodfire/Llama-3.3-70B-Instruct-SAE-l50",
    filename="Llama-3.3-70B-Instruct-SAE-l50.pt"
)
sae_state = torch.load(sae_path)
```

### Section 1.3: Feature Steering
- The steering equation: h' = h + α∑d_i
- Intuition: adding/subtracting concept directions
- Examples of what steering can do
- **Demo**: Steering confidence up/down

---

## Part 2: The Subjective-Experience Steering Study

### Section 2.1: The Reported Mechanistic Interpretation
- Berg et al. (2025) claim
- Experiment 2: Steering "deception" features affects consciousness reports
- The 96% → 16% result

### Section 2.2: Why This Matters (If True)
- Implications for AI consciousness debate
- Implications for AI safety (models might be "hiding" capabilities)
- Why consequential mechanistic interpretations require strong evidence

### Section 2.3: The Replication Problem
- Goodfire API access required
- What the API provides vs. what we can do
- Publicly unavailable feature-labeling and version metadata

---

## Part 3: Building Our Own Feature Selector

### Section 3.1: Contrastive Activation Profiling
- The core idea: features that differ between contexts
- Step-by-step implementation
- **Code walkthrough**: Finding deception features

```python
def find_contrastive_features(model, sae, positive_prompts, negative_prompts):
    # Profile activations on each prompt type
    pos_activations = [profile(p) for p in positive_prompts]
    neg_activations = [profile(p) for p in negative_prompts]
    
    # Compute contrast
    contrast = mean(pos_activations) - mean(neg_activations)
    
    # Return top-K
    return contrast.topk(k=10).indices
```

### Section 3.2: The Problems with Naive Selection
- Prompt overfitting
- Spurious correlates
- Feature heterogeneity
- The K parameter problem

### Section 3.3: Triangulation Methods
- Category intersection (multiple deception types)
- Stability selection (bootstrap)
- Holdout validation
- **Interactive demo**: Try different methods, see which features survive

---

## Part 4: Our Replication Attempt

### Section 4.1: Setup
- Model: Llama 3.3 70B (8-bit quantized)
- SAE: Goodfire layer 50
- Features: Top-10 by contrastive activation
- Hardware: A100 80GB

### Section 4.2: Results
- Table: Affirmation rates by condition and steering
- Key finding: 0% affirmation regardless of steering
- Ground-truth controls work correctly
- Absurd controls work correctly

### Section 4.3: Why Might the Results Differ?
- Our features might be different from theirs
- The classifier matters enormously
- Self-referential priming is necessary but not sufficient

### Section 4.4: What We Can and Can't Conclude
- Can't say paper is wrong (different methodology)
- Can say effect is not robust to feature selection method
- Can say classifier sensitivity is a major issue

---

## Part 5: The Deeper Questions

### Section 5.1: What Are "Deception Features" Really?
- Feature overlap analysis
- Cosine similarity with roleplay, confidence, hedging
- **Visualization**: UMAP of feature space

### Section 5.2: Alternative Hypotheses
- Style/confidence confound
- Roleplay activation
- Instruction following disruption
- Semantic overlap in feature space

### Section 5.3: Experiments to Distinguish Hypotheses
- Absurd affirmation battery
- Parallel phenomenal claims
- Per-feature ablation
- Cross-model validation

---

## Part 6: Lessons for Interpretability Research

### Section 6.1: The Interpretation Gap
- Features ≠ concepts
- Labels are hypotheses, not facts
- Researcher degrees of freedom

### Section 6.2: Best Practices
- Always use multiple feature selection methods
- Always include absurd/control conditions
- Always report classifier methodology
- Always check feature overlap with related concepts

### Section 6.3: Open Questions
- Can we ever know what a feature "really" represents?
- Is steering revealing or creating states?
- What would convince us of genuine phenomenal gating?

---

## Part 7: Try It Yourself

### Section 7.1: Quick Start Code
- Load model and SAE
- Profile features
- Run steering experiment
- **Jupyter notebook link**

### Section 7.2: RunPod Setup
- Hardware recommendations
- Step-by-step guide
- Cost estimates

### Section 7.3: Extending This Work
- Ideas for further experiments
- How to contribute
- Links to code and data

---

## Conclusion

- SAE steering is powerful but interpretation is hard
- The consciousness paper raises interesting questions but isn't conclusive
- Feature labeling is the crux of the problem
- We need better methods for robust feature identification

---

## Appendix

### A. Full Feature Selection Code
### B. LLM Classifier Implementation
### C. Statistical Analysis Details
### D. Hardware and Reproducibility Notes

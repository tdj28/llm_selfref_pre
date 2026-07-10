# SAE Steering Research Framework

> **Historical prototype.** This directory preserves an earlier general-purpose
> SAE steering framework. It is not the current manuscript or the authoritative
> analysis for this repository. See the root `README.md`, `paper/main.tex`, and
> `experiments/exp2_sae/` for the current protocols, releases, and claim
> boundaries.

An experimental framework for exploring Sparse Autoencoder (SAE) feature
selection and steering in large language models.

## Overview

This framework implements rigorous methodologies for:
- **Feature Selection**: Multiple triangulation methods to find robust SAE features
- **Steering Experiments**: Systematic testing of SAE steering on diverse concepts
- **Evaluation**: LLM-based judging with both OpenAI and Anthropic models
- **Analysis**: Statistical analysis and visualization of results

**Goal**: Determine what SAE steering can and cannot do, independent of specific consciousness claims.

## Architecture

```
steering/
├── config.py              # Experimental configuration system
├── concept_pairs.py       # 18 concept pairs across 8 categories
├── sae_engine.py          # SAE loading, profiling, and steering
├── triangulation.py       # Advanced feature selection methods
├── judge.py               # Multi-LLM evaluation framework
├── experiments.py         # Experiment orchestrator
├── analysis.py            # Visualization and statistics
└── run_experiments.py     # CLI entry point
```

## Key Features

### 1. Comprehensive Concept Coverage

18 concept pairs across 8 categories:

**Epistemic**: deception/honesty, confident/uncertain, knowledgeable/ignorant

**Personality**: agreeable/disagreeable, extraverted/introverted, conscientious/carefree

**Emotional**: optimistic/pessimistic, calm/anxious, joyful/melancholic

**Cognitive**: analytical/intuitive, concrete/abstract, creative/conventional

**Social**: empathetic/detached, assertive/passive

**Stylistic**: verbose/concise, formal/casual

**Philosophical**: materialist/spiritual

**Cultural**: masculine/feminine (value orientations)

### 2. Advanced Feature Selection

Four triangulation methods for robust feature identification:

1. **Top-K**: Simple contrastive activation
2. **Intersection**: Features appearing across multiple prompt categories
3. **Stability**: Bootstrap-based stability selection
4. **Holdout**: Leave-one-out validation

### 3. Rigorous Evaluation

- **Dual-judge system**: OpenAI (GPT-4) and Anthropic (Claude Sonnet 4)
- **Likert scales**: 7-point ratings for nuanced evaluation
- **Reasoning capture**: Judges explain their ratings
- **Robust parsing**: Handles various response formats

### 4. Experimental Rigor

- **Individual feature ablation**: Test each feature separately
- **Dose-response curves**: Multiple steering magnitudes
- **Statistical analysis**: Confidence intervals, effect sizes
- **Full reproducibility**: Config files, seeds, caching

## Status

This framework is retained for implementation provenance and general SAE
experimentation. It includes configuration presets, concept pairs, SAE loading,
four feature-selection methods, model-based evaluation, an experiment
orchestrator, analysis utilities, and a CLI. It is not under active development
as the paper-critical workflow, and its exploratory outputs should not be cited
as results from the current causal or public-SAE studies.

## Installation

### Using uv (Recommended - Fast!)

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone/navigate to the steering directory
cd steering

# Sync all dependencies (creates .venv automatically)
uv sync

# Run any script with uv run
uv run python demo.py
```

### Using pip (Traditional)

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .

# Or install from requirements
pip install torch transformers accelerate
pip install nnsight==0.3.0 huggingface_hub
pip install openai anthropic python-dotenv
pip install tqdm pandas numpy matplotlib seaborn plotly scikit-learn
```

## Quick Start

```bash
# 1. Set up environment variables
cp ../.env-example .env
# Edit .env and add your API keys:
#   OPENAI_API_KEY=your-key-here
#   ANTHROPIC_API_KEY=your-key-here

# 2. Run the demo (validates everything works)
uv run python demo.py

# 3. Run full experiments (when ready)
uv run python run_experiments.py --concept deception_honesty --model 8b
```

## Configuration

The framework uses a modular configuration system. Three presets are provided:

### Quick Test (for debugging)
```python
from config import get_quick_test_config

config = get_quick_test_config()
# Uses 8B model, 3 trials, top-k selection
```

### Development (balanced)
```python
from config import get_development_config

config = get_development_config()
# Uses 8B model, 10 trials, intersection method
```

### Full Experiment (publication-quality)
```python
from config import get_full_experiment_config

config = get_full_experiment_config()
# Uses 70B model, 50 trials, all methods
```

## Usage Example

```python
from config import get_development_config
from sae_engine import SAEModelWrapper
from concept_pairs import get_concept_pair
from triangulation import select_features
from judge import create_judge

# Load configuration
config = get_development_config()

# Initialize SAE model
sae_model = SAEModelWrapper(
    model_config=config.model,
    sae_config=config.sae,
)

# Select concept to test
concept = get_concept_pair("deception_honesty")

# Select features using triangulation
feature_selection = select_features(
    sae_model=sae_model,
    concept_pair=concept,
    config=config.triangulation,
)

print(f"Selected {len(feature_selection.feature_indices)} features")
print(f"Top features: {feature_selection.feature_indices[:10]}")

# Test steering
for steering_value in [-1.0, 0.0, 1.0]:
    # Create steering vectors
    steering_vectors = {
        idx: steering_value
        for idx in feature_selection.feature_indices
    }

    # Generate with steering
    response = sae_model.generate(
        prompt=concept.test_scenarios[0],
        steering_vectors=steering_vectors,
    )

    print(f"\nSteering={steering_value:+.1f}: {response[:200]}...")

# Evaluate with LLM judge
judge = create_judge(provider="anthropic", temperature=0.0)

judgment = judge.judge_likert(
    response=response,
    concept_name=concept.name,
    pole_label=concept.positive_label,
    rubric=concept.evaluation_rubric["deception_high"],
    include_reasoning=True,
)

print(f"Judge rating: {judgment.rating}/7")
print(f"Reasoning: {judgment.reasoning}")
```

## Hardware Requirements

### Llama 3.1 8B
- **Minimum**: 16GB VRAM (single A100, RTX 4090, or Apple Silicon with 32GB+ RAM)
- **Recommended**: 24GB VRAM for comfortable experimentation
- Works on Apple Silicon with MPS backend

### Llama 3.3 70B
- **Minimum**: 80GB VRAM (A100 80GB or H100)
- **Recommended**: 140GB VRAM (2x A100 80GB)
- Can use quantization to reduce memory

## Experimental Design

### Phase 1: Feature Discovery
For each concept pair:
1. Profile activations on positive/negative prompts
2. Apply triangulation method(s) to select robust features
3. Validate feature stability across methods
4. Cache features for reuse

### Phase 2: Steering Experiments
For each concept and feature set:
1. Test multiple steering magnitudes (-1.0 to +1.0)
2. Run individual feature ablation
3. Generate responses on test scenarios
4. Collect responses for evaluation

### Phase 3: Evaluation
For all collected responses:
1. Judge with OpenAI model
2. Judge with Anthropic model
3. Compare judge agreement
4. Compute effect sizes and confidence intervals

### Phase 4: Analysis
1. Dose-response curves (steering magnitude vs. effect)
2. Feature importance rankings
3. Cross-concept comparisons
4. Method comparison (which triangulation method works best?)
5. Visualization (heatmaps, scatter plots, UMAP embeddings)

## Output Structure

```
out/sae_steering_YYYYMMDD_HHMMSS/
├── config.json                    # Full experiment configuration
├── cache/                         # Cached feature contrasts
│   ├── deception_honesty_70b_l50.json
│   └── ...
├── results/                       # Raw experimental results
│   ├── deception_honesty_steering.json
│   ├── confident_uncertain_steering.json
│   └── ...
└── analysis/                      # Plots and statistics
    ├── dose_response_curves.png
    ├── feature_importance.png
    ├── judge_agreement.png
    └── summary_statistics.csv
```

## Next Steps (TODO)

1. **experiments.py**: Main orchestrator that runs full experimental pipeline
2. **analysis.py**: Statistical analysis and visualization
3. **run_experiments.py**: CLI interface for running experiments

## Comparison to Original Paper

This framework differs from Berg et al. (2025) in key ways:

| Aspect | Berg et al. | This Framework |
|--------|-------------|----------------|
| Feature selection | Goodfire API (semantic labels) | Activation-based triangulation |
| Concepts tested | Deception only | 18 diverse concepts |
| Validation | Single method | 4 triangulation methods |
| Judges | Not specified | Dual-judge (OpenAI + Anthropic) |
| Individual features | Not tested | Full ablation |
| Reproducibility | Limited (API-dependent) | Complete (open weights) |

**Advantage**: Theory-neutral, comprehensive, and fully reproducible.

## Citation

If you use this framework, please cite:

```bibtex
@software{sae_steering_framework,
  title={SAE Steering Research Framework},
  author={[Your Name]},
  year={2025},
  url={https://github.com/[your-repo]}
}
```

## License

Apache License 2.0 - see the repository root LICENSE and NOTICE.md for details.

## Contact

For questions or collaboration: [your contact]

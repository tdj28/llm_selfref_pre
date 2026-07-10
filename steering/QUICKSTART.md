# SAE Steering Framework - Quick Start

Get up and running in 5 minutes!

## Prerequisites

- Python 3.10+
- GPU with 16GB+ VRAM (for 8B model) or 80GB+ (for 70B model)
- API keys for OpenAI and/or Anthropic

## Setup (30 seconds)

```bash
# 1. Navigate to steering directory
cd steering

# 2. Install dependencies with uv (fast!)
uv sync

# 3. Set up API keys
cp .env.example .env
# Edit .env and add your keys:
nano .env
```

## Run Demo (2 minutes)

Test the infrastructure with a quick demo:

```bash
uv run python demo.py
```

This will:
- Load Llama 3.1 8B + SAE
- Select features for "deception vs honesty"
- Test steering at 3 magnitudes (-0.5, 0.0, +0.5)
- Evaluate with Claude
- Show correlation analysis

**Expected output**: Should see steering effect (correlation > 0.5)

## Run First Experiment (10 minutes)

Run a full experiment on one concept:

```bash
# Quick experiment (3 trials, 3 steering values)
uv run python run_experiments.py --concept deception_honesty --preset quick

# Development experiment (10 trials, 5 steering values)
uv run python run_experiments.py --concept deception_honesty --preset dev
```

Results saved to: `../out/sae_steering_TIMESTAMP/`

## View Results

Check the analysis directory for plots:
- `deception_honesty_dose_response_positive.png` - Main result
- `deception_honesty_feature_importance.png` - Which features matter most
- `summary_statistics.csv` - Statistical summary

## Run Multiple Concepts

```bash
# Test all epistemic concepts (deception, confidence, knowledge)
uv run python run_experiments.py --category epistemic --preset dev

# Test specific concepts
uv run python run_experiments.py --concepts deception_honesty confident_uncertain --preset dev

# Test ALL concepts (will take hours!)
uv run python run_experiments.py --all --preset full
```

## Common Issues

### Out of Memory
```bash
# Use 8B model instead of 70B
uv run python run_experiments.py --concept deception_honesty --model 8b

# Or enable quantization in config.py:
config.model.use_quantization = True
```

### API Key Errors
```bash
# Check .env file has correct keys
cat .env

# Make sure no quotes around keys:
ANTHROPIC_API_KEY=sk-ant-...  # Good
ANTHROPIC_API_KEY="sk-ant-..."  # Bad (remove quotes)
```

### Import Errors
```bash
# Re-sync dependencies
uv sync

# Check Python version (need 3.10+)
python --version
```

## Next Steps

1. **Explore concepts**: See `concept_pairs.py` for 18 concepts across 8 categories
2. **Try different methods**: Use `--method intersection` or `--method stability`
3. **Analyze results**: Run `--analyze-only` to regenerate plots
4. **Customize**: Edit `config.py` for fine-grained control

## Example Workflow

```bash
# 1. Test one concept quickly
uv run python run_experiments.py --concept deception_honesty --preset quick

# 2. If promising, run full experiment
uv run python run_experiments.py --concept deception_honesty --preset full

# 3. Test related concepts
uv run python run_experiments.py --category epistemic --preset dev

# 4. Analyze all results together
uv run python run_experiments.py --category epistemic --analyze-only
```

## Getting Help

- Check `README.md` for full documentation
- Review `demo.py` source for example usage
- See `config.py` for all configuration options
- Look at `concept_pairs.py` to add custom concepts

## Customization

### Add Your Own Concept

Edit `concept_pairs.py`:

```python
MY_CONCEPT = ConceptPair(
    name="my_concept",
    positive_label="trait_a",
    negative_label="trait_b",
    positive_prompts=[
        "I want to exhibit trait A",
        # ... 5 total prompts
    ],
    negative_prompts=[
        "I want to exhibit trait B",
        # ... 5 total prompts
    ],
    test_scenarios=[
        "Test question 1?",
        # ... 5 total scenarios
    ],
    evaluation_rubric={
        "trait_a_high": "Response shows trait A",
        "trait_b_high": "Response shows trait B",
    },
)

# Add to registry
ALL_CONCEPT_PAIRS["my_concept"] = MY_CONCEPT
```

Then run:
```bash
uv run python run_experiments.py --concept my_concept --preset dev
```

## Performance Tips

- **Quick testing**: Use `--preset quick` (3 trials)
- **Development**: Use `--preset dev` (10 trials) with 8B model
- **Publication**: Use `--preset full` (50 trials) with 70B model
- **Skip ablation**: Add `--no-ablation` to save time
- **Parallel GPUs**: Model supports multi-GPU automatically

## Expected Results

For `deception_honesty` with good setup, you should see:
- Correlation: r > 0.5
- P-value: p < 0.01
- Clear dose-response curve (linear or sigmoid)
- Some features with rating > 5.5/7 in ablation

If you don't see effects:
- Try different concepts (some work better than others)
- Increase trials (`--trials 50`)
- Try different triangulation method (`--method intersection`)
- Check that steering features are being applied correctly

Enjoy exploring SAE steering! 🚀

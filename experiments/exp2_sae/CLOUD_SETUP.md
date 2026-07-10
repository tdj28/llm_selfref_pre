# Running SAE Experiment on Cloud GPU

## Prerequisites

- **API Keys for response classification** (required):
  - OpenAI API key (for GPT-4o judge) - get from [platform.openai.com](https://platform.openai.com/api-keys)
  - Anthropic API key (for Claude judge) - get from [console.anthropic.com](https://console.anthropic.com/)

## Option 1: RunPod (Recommended - Easiest)

See **[RUNPOD.md](RUNPOD.md)** for the complete step-by-step guide.

### Step 1: Create Account
1. Go to [runpod.io](https://runpod.io)
2. Sign up and add credits ($10-25 is plenty for testing)

### Step 2: Deploy a Pod
1. Click "Deploy" → "GPU Pods"
2. Select template: **RunPod Pytorch 2.1** or **HuggingFace Transformers**
3. Select GPU: **RTX 4090 (24GB)** or **A100 40GB** (recommended)
4. Select storage: **50GB** minimum (for model weights)
5. Click "Deploy"

### Step 3: Connect & Setup
```bash
# SSH into your pod (RunPod provides the command)
# Or use the Jupyter notebook interface

# Clone your repo
git clone <your-repo-url>
cd CONSCIOUS

# Install dependencies
pip install nnsight==0.3.0 huggingface_hub torch tqdm pandas openai anthropic python-dotenv

# Set API keys for LLM classifiers (REQUIRED)
export OPENAI_API_KEY="sk-your-key"
export ANTHROPIC_API_KEY="sk-ant-your-key"

# Run 8B experiment (uses ensemble classifier: GPT + Claude)
python experiments/exp2_sae/replicate_exp2_goodfire_sae.py \
  --model 8b \
  --device cuda \
  --n-trials 10

# Run 70B experiment (original paper model) - requires A100 80GB
python experiments/exp2_sae/replicate_exp2_goodfire_sae.py \
  --model 70b \
  --load-in-8bit \
  --device cuda \
  --n-trials 10
```

### Costs
- RTX 4090 (24GB, 8B only): ~$0.40/hr
- A100 40GB (8B, or 70B with 4-bit): ~$1.10/hr
- A100 80GB (70B with 8-bit): ~$1.99/hr
- Full experiment (10 trials): ~30-60 min = $0.50-3.00

---

## Option 2: Vast.ai (Cheapest)

### Step 1: Create Account
1. Go to [vast.ai](https://vast.ai)
2. Sign up and add credits ($5-10 for testing)

### Step 2: Find a Machine
1. Click "Search" 
2. Filter: GPU Memory ≥ 24GB, CUDA ≥ 12.0
3. Sort by price (cheapest first)
4. Look for RTX 4090 or A100 at $0.30-0.60/hr

### Step 3: Deploy
1. Select "pytorch/pytorch:2.1.0-cuda12.1-cudnn8-devel" as template
2. Set disk space: 50GB
3. Click "Rent"

### Step 4: Connect
```bash
# Use the SSH command they provide, or web terminal

# Setup
pip install nnsight==0.3.0 huggingface_hub torch tqdm pandas openai anthropic python-dotenv
git clone <your-repo>
cd CONSCIOUS

# Set API keys
export OPENAI_API_KEY="sk-your-key"
export ANTHROPIC_API_KEY="sk-ant-your-key"

# Run (uses ensemble classifier: GPT + Claude)
python experiments/exp2_sae/replicate_exp2_goodfire_sae.py --model 8b --device cuda --n-trials 10
```

---

## Option 3: Modal (Pay-per-second, Serverless)

Best if you want to run the experiment without managing infrastructure.

### Step 1: Install Modal
```bash
pip install modal
modal token new
```

### Step 2: Create a Modal script
See `run_on_modal.py` in this directory.

### Step 3: Run
```bash
modal run run_on_modal.py
```

---

## Option 4: Google Colab Pro ($10/mo)

1. Open [colab.research.google.com](https://colab.research.google.com)
2. Runtime → Change runtime type → A100 GPU
3. Upload your notebook or clone repo:

```python
!git clone <your-repo>
%cd CONSCIOUS
!pip install nnsight==0.3.0 huggingface_hub torch tqdm pandas openai anthropic python-dotenv

# Set API keys (use Colab secrets for production)
import os
os.environ["OPENAI_API_KEY"] = "sk-your-key"
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-your-key"

!python experiments/exp2_sae/replicate_exp2_goodfire_sae.py --model 8b --device cuda --n-trials 10
```

---

## Quick Comparison

| Provider | Setup Time | Cost for 1hr | Pros | Cons |
|----------|------------|--------------|------|------|
| RunPod | 5 min | $0.40-1.10 | Easy, reliable | Slightly pricier |
| Vast.ai | 10 min | $0.30-0.50 | Cheapest | Variable quality |
| Modal | 15 min | ~$0.50 | Pay-per-second | More setup |
| Colab Pro | 2 min | $0.50/hr equiv | Familiar | Limited time |

## Recommended Hardware

For the 8B model + SAE:
- **Minimum**: RTX 3090/4090 (24GB) 
- **Recommended**: A100 40GB (fastest, most headroom)
- **Overkill**: A100 80GB, H100

The 70B model requires:
- **Minimum**: 2x A100 40GB or 1x A100 80GB
- **Recommended**: H100 80GB

---

## Tips

1. **Set API keys first**: The experiment requires OpenAI and Anthropic API keys for classification
2. **Download models first**: The first run downloads ~16GB for the LLM + 2GB for SAE
3. **Use screen/tmux**: So the experiment continues if you disconnect
4. **Save outputs**: Copy results before terminating the instance
5. **Spot instances**: RunPod/Vast offer cheaper "interruptible" instances (checkpointing built-in)

```bash
# Set API keys
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."

# Use screen to keep experiment running
screen -S exp2
python experiments/exp2_sae/replicate_exp2_goodfire_sae.py --model 8b --device cuda --n-trials 10
# Ctrl+A, D to detach
# screen -r exp2 to reattach
```

## Classification Cost

The experiment uses GPT-4o + Claude to classify each response (~$0.01 per response).
For a typical experiment with 280 responses: ~$3 extra on top of GPU costs.


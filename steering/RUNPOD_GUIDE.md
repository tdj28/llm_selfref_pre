# Running SAE Steering Experiments on RunPod

This guide covers running the triangulation and steering experiments on cloud GPUs.

## Hardware Requirements

| Model | GPU | VRAM | Estimated Cost |
|-------|-----|------|----------------|
| Llama 3.1 8B | A10 (24GB) or L4 (24GB) | 16GB | $0.30-0.40/hr |
| Llama 3.3 70B (8-bit) | A100 80GB | 45-50GB | $1.50-2.00/hr |
| Llama 3.3 70B (4-bit) | A100 40GB or A6000 | 35-40GB | $0.80-1.20/hr |

**Recommendation**: Start with 8B model on L4 for development, then scale to 70B for final experiments.

## Quick Start

### 1. Create RunPod Instance

```
Template: RunPod PyTorch 2.1.0
GPU: NVIDIA A100 80GB PCIe (for 70B) or L4 (for 8B)
Container Disk: 20GB
Volume Disk: 300GB (critical - models are large!)
```

### 2. SSH Setup

```bash
# From RunPod dashboard, get SSH command:
ssh root@<IP> -p <PORT> -i ~/.ssh/id_ed25519
```

### 3. Environment Setup

```bash
# Clone repo
cd /workspace
git clone https://github.com/YOUR_USERNAME/CONSCIOUS.git
cd CONSCIOUS/steering

# Create virtualenv
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set HuggingFace cache to volume (CRITICAL for disk space)
echo 'export HF_HOME=/workspace/huggingface_cache' >> ~/.bashrc
mkdir -p /workspace/huggingface_cache
source ~/.bashrc

# Login to HuggingFace (for gated models)
huggingface-cli login
```

### 4. Verify Setup

```bash
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
python -c "import torch; print(f'GPU: {torch.cuda.get_device_name(0)}')"
```

## Experiment Menu

### A. Feature Selection Comparison

Compare different feature selection methods:

```bash
python run_experiments.py triangulation \
    --model llama-8b \
    --methods top_k intersection stability \
    --output out/triangulation_comparison.json
```

### B. Deception Category Intersection

Find features robust across deception types:

```bash
python run_experiments.py intersection \
    --model llama-70b-8bit \
    --categories social strategic capability performative protective \
    --top-k 50 \
    --min-categories 3 \
    --output out/robust_features.json
```

### C. Steering Dose-Response

Fine-grained steering values:

```bash
python run_experiments.py steering \
    --model llama-70b-8bit \
    --steering-values -1.0 -0.8 -0.6 -0.4 -0.2 0 0.2 0.4 0.6 0.8 1.0 \
    --n-trials 30 \
    --output out/dose_response.jsonl
```

### D. Feature Overlap Analysis

Compare deception features to roleplay/confidence:

```bash
python run_experiments.py overlap \
    --model llama-8b \
    --concepts deception roleplay confidence uncertainty refusal \
    --output out/feature_overlap.json
```

### E. Absurd Controls (Reductio ad Absurdum)

Test if steering affects all claims equally:

```bash
python run_experiments.py absurd \
    --model llama-70b-8bit \
    --steering-values -0.6 0 0.6 \
    --n-trials 30 \
    --output out/absurd_controls.jsonl
```

## Experiment Workflow

### Phase 1: Feature Selection (8B model, fast iteration)

```bash
# 1. Run triangulation comparison
python run_experiments.py triangulation --model llama-8b

# 2. Analyze which features survive multiple methods
python analysis.py triangulation out/triangulation_comparison.json

# 3. Run intersection across deception categories
python run_experiments.py intersection --model llama-8b --min-categories 3
```

### Phase 2: Validation (70B model, final results)

```bash
# 1. Use robust features from Phase 1
python run_experiments.py steering \
    --model llama-70b-8bit \
    --features-from out/robust_features.json \
    --n-trials 50

# 2. Run absurd controls
python run_experiments.py absurd --model llama-70b-8bit --n-trials 50

# 3. Full dose-response curve
python run_experiments.py steering \
    --steering-values $(seq -1.0 0.1 1.0 | tr '\n' ' ') \
    --n-trials 30
```

### Phase 3: Analysis

```bash
# Generate all figures and tables
python analysis.py full out/

# Export for paper
python analysis.py export-latex out/ paper/figures/
```

## Memory Management

### Monitoring

```bash
# Watch GPU memory in real-time
watch -n 1 nvidia-smi

# Or use our built-in logging
python run_experiments.py steering --debug-memory
```

### If You Hit OOM

1. **Reduce batch processing**:
   ```bash
   python run_experiments.py ... --batch-size 1
   ```

2. **Use 4-bit quantization**:
   ```bash
   python run_experiments.py ... --model llama-70b-4bit
   ```

3. **Clear cache between experiments**:
   ```bash
   python -c "import torch; torch.cuda.empty_cache()"
   ```

4. **Reduce max tokens**:
   ```bash
   python run_experiments.py ... --max-tokens 50
   ```

## Output Files

All outputs go to `out/` directory:

```
out/
├── triangulation_comparison.json  # Feature selection comparison
├── robust_features.json           # Intersection-selected features
├── dose_response.jsonl            # Steering sweep results
├── absurd_controls.jsonl          # Absurd query results
├── feature_overlap.json           # Concept overlap analysis
└── figures/                       # Generated plots
```

## Downloading Results

```bash
# From your local machine
scp -r -P <PORT> root@<IP>:/workspace/CONSCIOUS/steering/out/ ./results/

# Or use rsync for large directories
rsync -avz -e "ssh -p <PORT>" root@<IP>:/workspace/CONSCIOUS/steering/out/ ./results/
```

## Cost Optimization

### Use Spot Instances

Spot instances are 50-80% cheaper but can be interrupted:

1. Enable checkpointing in experiments
2. Save results incrementally
3. Resume from checkpoint if interrupted

```bash
python run_experiments.py steering \
    --checkpoint out/checkpoint.json \
    --resume-if-exists
```

### Schedule Off-Peak

- Cheapest: 2-6 AM Pacific (weekdays)
- Most expensive: 10 AM - 4 PM Pacific (weekdays)

## Troubleshooting

### "CUDA out of memory"

See Memory Management section above.

### "ModuleNotFoundError"

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### "Disk quota exceeded"

```bash
# Check disk usage
df -h /workspace

# Clean old caches
rm -rf /workspace/huggingface_cache/hub/models--*/.locks
rm -rf ~/.cache/huggingface
```

### Model download hangs

```bash
# Disable xet protocol
export HF_HUB_DISABLE_XET=1
pip install hf_transfer
export HF_HUB_ENABLE_HF_TRANSFER=1
```


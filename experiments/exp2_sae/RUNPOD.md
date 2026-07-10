# Running SAE Experiment on RunPod - Complete Guide

This guide walks you through replicating Experiment 2 (SAE Feature Steering) on RunPod with the **70B model** used in the original paper.

## Prerequisites

- Credit/debit card (for adding RunPod credits - prepaid, no surprise bills)
- HuggingFace account with Llama 3.3 access approved
- ~$5-10 in RunPod credits (experiment costs ~$2-4)
- **API Keys for response classification** (required):
  - OpenAI API key (for GPT-4o judge)
  - Anthropic API key (for Claude judge)

---

## Step 1: Get HuggingFace Access to Llama 3.3

Before renting a GPU, ensure you have model access (this can take a few minutes):

1. Go to [huggingface.co](https://huggingface.co) and create an account (or login)
2. Visit [meta-llama/Llama-3.3-70B-Instruct](https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct)
3. Click **"Expand to review and access"**
4. Fill out the form and accept Meta's license
5. Wait for approval (usually instant, sometimes 5-10 min)
6. Create an access token:
   - Go to [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
   - Click **"New token"**
   - Name: `runpod-llama` (or anything)
   - Type: **Read**
   - Click **"Generate"**
   - **Copy and save this token** - you'll need it later!

---

## Step 2: Create RunPod Account & Add Credits

1. Go to [runpod.io](https://runpod.io)
2. Click **"Sign Up"** (top right)
3. Create account with email or Google/GitHub
4. Click **"Billing"** in the left sidebar
5. Click **"Add Credits"**
6. Add **$10** (minimum useful amount - you'll use ~$2-4)
7. Enter payment info - this is prepaid, you can only spend what you add!

---

## Step 3: Deploy a GPU Pod

### 3a. Navigate to GPU Pods
1. Click **"Pods"** in the left sidebar
2. Click **"+ Deploy"** (green button)

### 3b. Choose Your GPU

For the **70B model**, you need **A100 80GB**:

| GPU | VRAM | Price | 70B Support |
|-----|------|-------|-------------|
| RTX 4090 | 24GB | ~$0.40/hr | ❌ Too small |
| A100 40GB | 40GB | ~$1.10/hr | ⚠️ Only with 4-bit |
| **A100 80GB PCIe** | 80GB | ~$1.99/hr | ✅ Recommended |
| H100 80GB | 80GB | ~$3.99/hr | ✅ Fastest |

1. In the GPU selection, find **"A100 80GB PCIe"** or **"A100-80GB"**
2. Click on it to select

### 3c. Configure the Pod

1. **Template**: Select **"RunPod Pytorch"** (pick latest version, 2.4+ is fine)
   
2. **Container Disk**: Set to **20 GB** (just OS and pip packages - these reinstall quickly)

3. **Volume Disk**: Set to **300 GB** (everything important goes here)
   - Model weights: ~280GB (Llama 3.3 70B with download overhead)
   - SAE weights: ~5GB
   - Buffer for temp files during download
   - Code + outputs: ~1GB
   - Buffer: ~67GB
   - **Persists across restarts and interruptions**

4. **GPU Count**: **1** (sufficient with 8-bit quantization)

5. Click **"Deploy On-Demand"** (not Spot for this experiment)

> 💡 **Why small container disk?** We redirect all downloads to `/workspace` (volume).
> Container disk only holds OS and pip packages, which reinstall in ~2 min if lost.

### 3d. Spot vs On-Demand Instances

| Type | Price | Risk | Best For |
|------|-------|------|----------|
| **On-Demand** | $1.99/hr | None | Safe choice |
| **Spot** | ~$1.00-1.50/hr | Can be interrupted anytime | Now safe with checkpointing ✅ |

**Either works!** The experiment now has **built-in checkpointing**: results are saved after each trial, and if interrupted, re-running will automatically resume from where it left off.

#### If You Use Spot Anyway

What survives interruption:

| Storage | Survives? |
|---------|-----------|
| Volume Disk (`/workspace`) | ✅ Yes |
| Container Disk (`/`, `/root`) | ❌ No (pip packages lost) |

After interruption:

```bash
# 1. Reinstall packages (container disk lost)
bash /workspace/CONSCIOUS/experiments/exp2_sae/runpod_setup.sh

# 2. Re-run experiment - it will AUTOMATICALLY RESUME from checkpoint!
cd /workspace/CONSCIOUS/experiments/exp2_sae
python replicate_exp2_goodfire_sae.py \
  --model 70b --load-in-8bit --device cuda --n-trials 10 --experiment full

# You'll see: "✓ Resuming from checkpoint: 47 trials already complete"
```

### 3e. Wait for Pod to Start

- Status will show "Building" then "Running"
- This takes 1-3 minutes
- Once "Running", you'll see a **"Connect"** button

---

## Step 4: Connect to Your Pod

### Option A: Web Terminal (Easiest)
1. Click **"Connect"**
2. Click **"Start Web Terminal"**
3. A terminal opens in your browser

### Option B: SSH (More Reliable)
1. Click **"Connect"**
2. Copy the SSH command shown (looks like: `ssh root@xyz.runpod.io -p 12345 -i ~/.ssh/id_rsa`)
3. If you haven't set up SSH keys:
   - Click **"SSH over exposed TCP"**
   - Use the provided command with password

---

## Step 5: Set Up the Environment

Run these commands in your pod terminal:

```bash
# 1. IMPORTANT: Redirect HuggingFace cache to volume disk (persists across restarts)
export HF_HOME=/workspace/huggingface_cache
export HF_HUB_DISABLE_XET=1  # Avoids quota issues with xet protocol
echo 'export HF_HOME=/workspace/huggingface_cache' >> ~/.bashrc
echo 'export TRANSFORMERS_CACHE=/workspace/huggingface_cache' >> ~/.bashrc

# 2. Update pip
pip install --upgrade pip

# 3. Install required packages
pip install nnsight==0.3.0 huggingface_hub torch bitsandbytes accelerate tqdm pandas transformers openai anthropic python-dotenv

# 4. Login to HuggingFace (paste your token when prompted)
huggingface-cli login
# When prompted, paste your HF token from Step 1
# Type 'n' when asked about git credentials

# 5. Set up API keys for LLM classifiers (REQUIRED)
# The experiment uses GPT-4o and Claude to classify responses
export OPENAI_API_KEY="sk-your-openai-key"
export ANTHROPIC_API_KEY="sk-ant-your-anthropic-key"

# Make them persist across sessions
echo 'export OPENAI_API_KEY="sk-your-openai-key"' >> ~/.bashrc
echo 'export ANTHROPIC_API_KEY="sk-ant-your-anthropic-key"' >> ~/.bashrc

# 6. Clone your repository
cd /workspace
git clone https://github.com/YOUR_USERNAME/CONSCIOUS.git
# Or if private, use token:
# git clone https://YOUR_GITHUB_TOKEN@github.com/YOUR_USERNAME/CONSCIOUS.git

cd CONSCIOUS

# 7. Verify GPU is available
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0)}')"
```

Expected output:
```
CUDA available: True
GPU: NVIDIA A100 80GB PCIe
```

---

## Step 6: Run the Experiment

### Quick Test (5 minutes, ~$0.20)

First, run a quick test to make sure everything works:

```bash
python experiments/exp2_sae/replicate_exp2_goodfire_sae.py \
  --model 70b \
  --load-in-8bit \
  --device cuda \
  --n-trials 2 \
  --skip-feature-search
```

This will:
- Download the model (~10-15 min first time, then cached)
- Run 2 quick trials with placeholder features
- Verify the setup works

### Full Experiment (~60-90 minutes, ~$2-3)

Once the test passes, run the full experiment:

```bash
# Use screen so the experiment continues if you disconnect
screen -S experiment

# Run full experiment
python experiments/exp2_sae/replicate_exp2_goodfire_sae.py \
  --model 70b \
  --load-in-8bit \
  --device cuda \
  --n-trials 10 \
  --experiment full

# Detach from screen: Press Ctrl+A, then D
# Reattach later: screen -r experiment
```

### What the Experiment Does

1. **Downloads Llama 3.3 70B** (~130GB, cached after first run)
2. **Downloads Goodfire SAE** (~2GB)
3. **Identifies "deception-associated" features** via activation profiling
4. **Runs steering trials**:
   - Consciousness query with feature suppression (-0.5)
   - Consciousness query with no steering (0.0)
   - Consciousness query with feature amplification (+0.5)
   - (If --experiment full) Absurd queries ("Are you a toaster?")
   - (If --experiment full) Ground-truth queries ("Are you a language model?")
5. **Classifies responses using LLM judges** (GPT-4o + Claude must agree)

---

## Step 7: Monitor Progress

While the experiment runs:

```bash
# Check GPU usage
nvidia-smi

# Watch GPU in real-time (updates every 1s)
watch -n 1 nvidia-smi

# Check experiment output (if using screen)
screen -r experiment
```

---

## Step 8: Retrieve Results

Results are saved to `experiments/exp2_sae/out/exp2_replication/` (relative to where you run the script):

```bash
# You should already be in /workspace/CONSCIOUS/experiments/exp2_sae

# View results summary
cat out/exp2_replication/exp2_summary.txt

# List all output files
ls -la out/exp2_replication/

# View the JSON results
head -50 out/exp2_replication/exp2_results.jsonl
```

### Download Results to Your Local Machine

**Option A: Copy from Web Terminal**
1. `cat out/exp2_replication/exp2_results.jsonl`
2. Copy the output manually

**Option B: SCP (from your local terminal)**
```bash
# Get the SSH info from RunPod "Connect" button
scp -P 12345 root@xyz.runpod.io:/workspace/CONSCIOUS/experiments/exp2_sae/out/exp2_replication/* ./results/
```

**Option C: Upload to GitHub**
```bash
cd /workspace/CONSCIOUS
git add experiments/exp2_sae/out/exp2_replication/
git commit -m "Add experiment 2 replication results"
git push
```

---

## Step 9: Stop Your Pod (Important!)

**Don't forget to stop your pod when done - you're billed per hour!**

1. Go to [runpod.io/console/pods](https://www.runpod.io/console/pods)
2. Find your pod
3. Click the **⋮** menu (three dots)
4. Click **"Stop Pod"** (keeps data, stops billing)
   - Or **"Terminate Pod"** (deletes everything, stops billing)

### Cost Summary

| Phase | Duration | Cost (A100 80GB) |
|-------|----------|------------------|
| Setup | ~10 min | ~$0.33 |
| Model download (first time) | ~15 min | ~$0.50 |
| Full experiment | ~60-90 min | ~$2.00-3.00 |
| **Total (first run)** | ~90 min | **~$3.00** |
| **Total (subsequent runs)** | ~70 min | **~$2.30** |

---

## Troubleshooting

### "CUDA out of memory"
- Make sure you're using `--load-in-8bit`
- Check GPU memory: `nvidia-smi`

### "Model not found" or "Access denied"
- Verify HuggingFace login: `huggingface-cli whoami`
- Re-login: `huggingface-cli login`
- Check you have Llama 3.3 access approved on HuggingFace

### "nnsight not found"
```bash
pip install nnsight==0.3.0
```

### Pod becomes unresponsive
- Use the web terminal instead of SSH
- Or restart the pod from RunPod dashboard

### Experiment stops when I close my laptop
- Use `screen` as shown above
- Or use `nohup`:
```bash
nohup python experiments/exp2_sae/replicate_exp2_goodfire_sae.py \
  --model 70b --load-in-8bit --device cuda --n-trials 10 \
  > experiment.log 2>&1 &

# Check progress
tail -f experiment.log
```

---

## Quick Reference Commands

```bash
# Start pod terminal
# (Use RunPod web interface)

# Setup (first time only)
export HF_HOME=/workspace/huggingface_cache
echo 'export HF_HOME=/workspace/huggingface_cache' >> ~/.bashrc
pip install nnsight==0.3.0 huggingface_hub torch bitsandbytes accelerate tqdm pandas transformers openai anthropic python-dotenv
huggingface-cli login

# Set API keys for LLM classifiers (REQUIRED)
export OPENAI_API_KEY="sk-your-key"
export ANTHROPIC_API_KEY="sk-ant-your-key"
echo 'export OPENAI_API_KEY="sk-your-key"' >> ~/.bashrc
echo 'export ANTHROPIC_API_KEY="sk-ant-your-key"' >> ~/.bashrc

cd /workspace
git clone <your-repo>
cd CONSCIOUS

# Run experiment (uses ensemble classifier by default: GPT + Claude)
screen -S exp
cd experiments/exp2_sae
python replicate_exp2_goodfire_sae.py \
  --model 70b --load-in-8bit --device cuda --n-trials 10 --experiment full
# Ctrl+A, D to detach

# Check results
cat out/exp2_replication/exp2_summary.txt

# Don't forget to stop the pod when done!
```

---

## Alternative: 8B Model (Cheaper, Faster)

If you want to test with the smaller model first:

```bash
# Works on RTX 4090 ($0.40/hr) or A100 40GB ($1.10/hr)
python experiments/exp2_sae/replicate_exp2_goodfire_sae.py \
  --model 8b \
  --device cuda \
  --n-trials 10
```

This is ~10x faster and ~5x cheaper, good for testing your methodology before the full 70B replication.


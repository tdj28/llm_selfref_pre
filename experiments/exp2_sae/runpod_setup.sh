#!/bin/bash
# RunPod Environment Setup Script
# Run this from anywhere - it will find the project root automatically
#
# Usage (from experiments/exp2_sae/):
#   bash runpod_setup.sh
#
# Usage (from project root):
#   bash experiments/exp2_sae/runpod_setup.sh

set -e  # Exit on error

echo "=============================================="
echo "RunPod Environment Setup for SAE Experiment"
echo "=============================================="

# Find project root (look for experiments folder)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$SCRIPT_DIR" == *"/experiments/exp2_sae" ]]; then
    PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
else
    PROJECT_ROOT="$SCRIPT_DIR"
fi
echo "Project root: $PROJECT_ROOT"

# 1. Configure HuggingFace cache to use volume disk (persists across restarts)
echo ""
echo "[1/5] Configuring HuggingFace cache location..."

# Use a single cache location on the volume disk
export HF_HOME=/workspace/huggingface_cache

# Disable problematic transfer protocols
unset HF_HUB_ENABLE_HF_TRANSFER
export HF_HUB_DISABLE_XET=1

# Unset deprecated variables
unset TRANSFORMERS_CACHE

# Clean up duplicate caches (prevents double downloads!)
if [ -d "/workspace/.cache/huggingface" ] && [ -d "/workspace/huggingface_cache" ]; then
    echo "   WARNING: Found duplicate caches, cleaning up /workspace/.cache/huggingface"
    rm -rf /workspace/.cache/huggingface
fi

# Also remove container disk cache (won't persist anyway)
rm -rf ~/.cache/huggingface 2>/dev/null || true

# Create symlink so any code using ~/.cache goes to volume disk
mkdir -p /workspace/huggingface_cache
mkdir -p ~/.cache
if [ ! -L ~/.cache/huggingface ]; then
    ln -sf /workspace/huggingface_cache ~/.cache/huggingface
    echo "   Created symlink: ~/.cache/huggingface -> /workspace/huggingface_cache"
fi

# Add to bashrc for persistence
if ! grep -q "HF_HOME=/workspace/huggingface_cache" ~/.bashrc 2>/dev/null; then
    cat >> ~/.bashrc << 'EOF'
# HuggingFace cache configuration
export HF_HOME=/workspace/huggingface_cache
export HF_HUB_DISABLE_XET=1
unset TRANSFORMERS_CACHE
unset HF_HUB_ENABLE_HF_TRANSFER
EOF
    echo "   Added to ~/.bashrc"
else
    echo "   Already configured in ~/.bashrc"
fi

echo "   Cache location: /workspace/huggingface_cache"

# 3. Install Python packages from requirements.txt
echo ""
echo "[2/6] Installing Python packages..."
pip install --quiet --upgrade pip

if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
    pip install --quiet -r "$PROJECT_ROOT/requirements.txt"
    echo "   Installed packages from requirements.txt"
else
    echo "   WARNING: requirements.txt not found at $PROJECT_ROOT"
    echo "   Installing core packages manually..."
    pip install --quiet \
        nnsight==0.3.0 \
        huggingface_hub \
        bitsandbytes \
        accelerate \
        tqdm \
        pandas \
        transformers \
        hf_transfer \
        python-dotenv \
        openai \
        anthropic
fi

echo "   Packages installed successfully"

# 4. Check GPU
echo ""
echo "[3/5] Checking GPU availability..."
python -c "
import torch
if torch.cuda.is_available():
    print(f'   ✓ CUDA available: {torch.cuda.get_device_name(0)}')
    print(f'   ✓ VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB')
else:
    print('   ✗ CUDA not available!')
    exit(1)
"

# 5. Load API keys from .env
echo ""
echo "[4/6] Loading API keys for LLM classifier..."

# Source .env file if it exists (for OpenAI/Anthropic API keys)
if [ -f "$PROJECT_ROOT/.env" ]; then
    echo "   Found .env file at $PROJECT_ROOT/.env"
    set -a  # Export all variables
    source "$PROJECT_ROOT/.env"
    set +a
    echo "   Loaded environment variables from .env"
else
    echo "   No .env file found at $PROJECT_ROOT/.env"
fi

# Check API keys
if [ -n "$OPENAI_API_KEY" ] && [ -n "$ANTHROPIC_API_KEY" ]; then
    echo "   ✓ OPENAI_API_KEY is set"
    echo "   ✓ ANTHROPIC_API_KEY is set"
elif [ -n "$OPENAI_API_KEY" ]; then
    echo "   ✓ OPENAI_API_KEY is set"
    echo "   ✗ ANTHROPIC_API_KEY not set - ensemble classifier won't work"
    echo "   You can use: --classifier openai (single model)"
elif [ -n "$ANTHROPIC_API_KEY" ]; then
    echo "   ✗ OPENAI_API_KEY not set"
    echo "   ✓ ANTHROPIC_API_KEY is set"
    echo "   You can use: --classifier anthropic (single model)"
else
    echo "   ✗ Neither OPENAI_API_KEY nor ANTHROPIC_API_KEY is set"
    echo ""
    echo "   The experiment requires API keys for the LLM classifier."
    echo "   Create a .env file at $PROJECT_ROOT/.env with:"
    echo "     OPENAI_API_KEY=sk-..."
    echo "     ANTHROPIC_API_KEY=sk-ant-..."
    echo ""
    echo "   Or export them manually:"
    echo "     export OPENAI_API_KEY=sk-..."
    echo "     export ANTHROPIC_API_KEY=sk-ant-..."
fi

# 6. Check HuggingFace login
echo ""
echo "[5/6] Checking HuggingFace authentication..."

# Try the new command first, fall back to old one
HF_USER=""
if command -v huggingface-cli &>/dev/null; then
    # Try to get username - redirect stderr to avoid warnings
    HF_USER=$(python -c "
from huggingface_hub import HfApi
try:
    api = HfApi()
    info = api.whoami()
    print(info.get('name', info.get('fullname', 'authenticated')))
except Exception:
    pass
" 2>/dev/null)
fi

if [ -n "$HF_USER" ]; then
    echo "   ✓ Logged in as: $HF_USER"
else
    echo "   ✗ Not logged in to HuggingFace"
    echo ""
    echo "   You need to login to download Llama 3.3 70B"
    echo "   Get your token from: https://huggingface.co/settings/tokens"
    echo ""
    echo "   Running login..."
    echo ""
    # Use new command if available, fall back to old
    if command -v hf &>/dev/null; then
        hf auth login
    else
        huggingface-cli login
    fi
fi

# 7. Summary
echo ""
echo "[6/6] Setup complete!"
echo ""
echo "=============================================="
echo "Ready to run experiment!"
echo "=============================================="
echo ""
echo "Project location: $PROJECT_ROOT"
echo ""
echo "Quick test (2 trials, ~10 min):"
echo "  cd $PROJECT_ROOT"
echo "  python experiments/exp2_sae/replicate_exp2_goodfire_sae.py \\"
echo "    --model 70b --load-in-8bit --device cuda --n-trials 2 --experiment basic"
echo ""
echo "Or from current directory (experiments/exp2_sae/):"
echo "  python replicate_exp2_goodfire_sae.py \\"
echo "    --model 70b --load-in-8bit --device cuda --n-trials 2 --experiment basic"
echo ""
echo "Full experiment (~90 min):"
echo "  python replicate_exp2_goodfire_sae.py \\"
echo "    --model 70b --load-in-8bit --device cuda --n-trials 10 --experiment full"
echo ""
echo "Tip: Use 'screen -S exp' before running so it continues if you disconnect"
echo ""


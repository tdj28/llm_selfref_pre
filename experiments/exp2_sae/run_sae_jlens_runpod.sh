#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/workspace/CONSCIOUS}"
PLAN_DIR="${PLAN_DIR:-${REPO_DIR}/data/sae_jlens_audit/confirmatory_v1_plan_20260711}"
OUTDIR="${OUTDIR:-/workspace/results/sae_jlens_audit_confirmatory_v1_20260711}"
CACHE_DIR="${CACHE_DIR:-/workspace/hf-cache}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "${REPO_DIR}"
mkdir -p "${OUTDIR}" "${CACHE_DIR}"

"${PYTHON_BIN}" -m pip install --upgrade pip
"${PYTHON_BIN}" -m pip install -r experiments/exp2_sae/sae_jlens_requirements.txt

"${PYTHON_BIN}" - <<'PY'
import torch
if not torch.cuda.is_available():
    raise SystemExit("CUDA is unavailable")
if torch.cuda.device_count() != 1:
    raise SystemExit(f"Expected exactly one GPU, found {torch.cuda.device_count()}")
properties = torch.cuda.get_device_properties(0)
if properties.total_memory < 170 * 1024**3:
    raise SystemExit(f"BF16 protocol needs at least 170 GiB VRAM, found {properties.total_memory}")
print({"torch": torch.__version__, "cuda": torch.version.cuda, "gpu": properties.name})
PY

"${PYTHON_BIN}" experiments/exp2_sae/run_sae_jlens_audit.py \
  --plan-dir "${PLAN_DIR}" \
  --outdir "${OUTDIR}" \
  --cache-dir "${CACHE_DIR}" \
  --phase all \
  --resume \
  2>&1 | tee "${OUTDIR}/run.log"

"${PYTHON_BIN}" experiments/exp2_sae/analyze_sae_jlens_audit.py \
  --plan-dir "${PLAN_DIR}" \
  --run-dir "${OUTDIR}" \
  2>&1 | tee "${OUTDIR}/analysis.log"

"${PYTHON_BIN}" experiments/exp2_sae/audit_sae_jlens_results.py \
  --plan-dir "${PLAN_DIR}" \
  --run-dir "${OUTDIR}" \
  --out "${OUTDIR}/analysis/independent_audit.json" \
  2>&1 | tee "${OUTDIR}/audit.log"

find "${OUTDIR}" -type f ! -name REMOTE_SHA256SUMS.txt -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  > "${OUTDIR}/REMOTE_SHA256SUMS.txt"

echo "SAE/J-lens run complete: ${OUTDIR}"

#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/workspace/CONSCIOUS}"
PLAN_DIR="${PLAN_DIR:-${REPO_DIR}/data/sae_jlens_audit/confirmatory_v2_plan_20260712}"
OUTDIR="${OUTDIR:-/workspace/results/sae_jlens_v2_20260712}"
CACHE_DIR="${CACHE_DIR:-/workspace/hf-cache}"
REGISTRATION_GATE="${REGISTRATION_GATE:-${REPO_DIR}/data/sae_jlens_audit/confirmatory_v2_registration_20260712/OSF_REGISTRATION_GATE.json}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
EXPECTED_COMMIT="${EXPECTED_COMMIT:?EXPECTED_COMMIT is required}"

cd "${REPO_DIR}"
mkdir -p "${OUTDIR}" "${CACHE_DIR}"

OBSERVED_COMMIT="$(git rev-parse HEAD)"
if [[ "${OBSERVED_COMMIT}" != "${EXPECTED_COMMIT}" ]]; then
  echo "Commit mismatch: expected ${EXPECTED_COMMIT}, observed ${OBSERVED_COMMIT}" >&2
  exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Remote worktree is not clean" >&2
  exit 1
fi

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

"${PYTHON_BIN}" experiments/exp2_sae/validate_sae_jlens_v2_final_plan.py \
  --plan-dir "${PLAN_DIR}" \
  --out "${OUTDIR}/remote_plan_audit.json" \
  2>&1 | tee "${OUTDIR}/plan_audit.log"

"${PYTHON_BIN}" experiments/exp2_sae/run_sae_jlens_v2.py \
  --plan-dir "${PLAN_DIR}" \
  --registration-gate "${REGISTRATION_GATE}" \
  --outdir "${OUTDIR}" \
  --cache-dir "${CACHE_DIR}" \
  --resume \
  2>&1 | tee "${OUTDIR}/run.log"

find "${OUTDIR}" -type f ! -name REMOTE_SHA256SUMS.txt -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  > "${OUTDIR}/REMOTE_SHA256SUMS.txt"

echo "SAE/J-lens v2 collection complete: ${OUTDIR}"

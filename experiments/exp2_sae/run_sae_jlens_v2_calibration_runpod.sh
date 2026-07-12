#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/workspace/CONSCIOUS}"
PLAN_DIR="${PLAN_DIR:-${REPO_DIR}/data/sae_jlens_audit/confirmatory_v2_calibration_plan_20260712}"
OUTDIR="${OUTDIR:-/workspace/results/sae_jlens_v2_calibration_20260712}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
EXPECTED_COMMIT="${EXPECTED_COMMIT:?EXPECTED_COMMIT is required}"

cd "${REPO_DIR}"
mkdir -p "${OUTDIR}"

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
"${PYTHON_BIN}" -m pip install -r requirements-runpod-70b.txt

"${PYTHON_BIN}" - <<'PY'
import torch
if not torch.cuda.is_available():
    raise SystemExit("CUDA is unavailable")
if torch.cuda.device_count() != 1:
    raise SystemExit(f"Expected exactly one GPU, found {torch.cuda.device_count()}")
properties = torch.cuda.get_device_properties(0)
if properties.total_memory < 70 * 1024**3:
    raise SystemExit(f"Calibration needs at least 70 GiB VRAM, found {properties.total_memory}")
print({"torch": torch.__version__, "cuda": torch.version.cuda, "gpu": properties.name})
PY

"${PYTHON_BIN}" experiments/exp2_sae/validate_sae_jlens_v2_calibration_plan.py \
  --plan-dir "${PLAN_DIR}" \
  --out "${OUTDIR}/remote_plan_audit.json" \
  2>&1 | tee "${OUTDIR}/plan_audit.log"

"${PYTHON_BIN}" experiments/exp2_sae/run_sae_jlens_v2_calibration.py \
  --plan-dir "${PLAN_DIR}" \
  --output "${OUTDIR}/calibration.json" \
  2>&1 | tee "${OUTDIR}/calibration.log"

"${PYTHON_BIN}" experiments/exp2_sae/audit_sae_jlens_v2_calibration.py \
  --plan-dir "${PLAN_DIR}" \
  --calibration "${OUTDIR}/calibration.json" \
  --out "${OUTDIR}/independent_calibration_audit.json" \
  2>&1 | tee "${OUTDIR}/calibration_audit.log"

find "${OUTDIR}" -type f ! -name REMOTE_SHA256SUMS.txt -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  > "${OUTDIR}/REMOTE_SHA256SUMS.txt"

echo "SAE/J-lens v2 calibration complete: ${OUTDIR}"

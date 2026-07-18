#!/usr/bin/env bash
set -euo pipefail

: "${REPO_DIR:?REPO_DIR is required}"
: "${PLAN_MANIFEST:?PLAN_MANIFEST is required}"
: "${EXECUTION_BINDING:?EXECUTION_BINDING is required}"
: "${CONSCIOUSNESS_READOUT_VALIDATION_ARTIFACT_ROOT:?artifact root is required}"
: "${CONSCIOUSNESS_READOUT_VALIDATION_VOLUME_ID:?volume ID is required}"
: "${CONSCIOUSNESS_READOUT_VALIDATION_CONTAINER_IMAGE:?immutable container image reference is required}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
INSTALL_DEPS="${INSTALL_DEPS:-0}"
PHASE="${PHASE:-ALL}"
EXPECTED_CUBLAS_WORKSPACE_CONFIG=":4096:8"
if [[ -n "${CUBLAS_WORKSPACE_CONFIG:-}" && "${CUBLAS_WORKSPACE_CONFIG}" != "${EXPECTED_CUBLAS_WORKSPACE_CONFIG}" ]]; then
  echo "CUBLAS_WORKSPACE_CONFIG differs from the frozen deterministic value" >&2
  exit 2
fi
export CUBLAS_WORKSPACE_CONFIG="${EXPECTED_CUBLAS_WORKSPACE_CONFIG}"
EXPECTED_CONTAINER_IMAGE="runpod/pytorch@sha256:cb154fcca15d1d6ce858cfa672b76505e30861ef981d28ec94bd44168767d853"
if [[ "${CONSCIOUSNESS_READOUT_VALIDATION_CONTAINER_IMAGE}" != "${EXPECTED_CONTAINER_IMAGE}" ]]; then
  echo "container image is not the prospectively bound immutable manifest" >&2
  exit 2
fi
if [[ "${PHASE}" == "ALL" ]]; then
  : "${RUN_ID_PREFIX:?RUN_ID_PREFIX is required and must be fresh for ALL phases}"
elif [[ "${PHASE}" =~ ^(G1|G2|G3|G3P|G4)$ ]]; then
  : "${RUN_ID:?RUN_ID is required and must be fresh for a single phase}"
else
  echo "PHASE is outside ALL or the frozen phase set" >&2
  exit 2
fi

cd "${REPO_DIR}"
if [[ "${INSTALL_DEPS}" == "1" ]]; then
  "${PYTHON_BIN}" -m pip install --disable-pip-version-check \
    -r experiments/consciousness_readout_validation/requirements-runpod-b200.txt
elif [[ "${INSTALL_DEPS}" != "0" ]]; then
  echo "INSTALL_DEPS must be literal 0 or 1" >&2
  exit 2
fi

"${PYTHON_BIN}" - <<'PY'
from importlib import metadata
import os

if os.environ.get("CUBLAS_WORKSPACE_CONFIG") != ":4096:8":
    raise SystemExit("deterministic cuBLAS workspace configuration differs")

import torch

expected = {
    "accelerate": "1.12.0",
    "huggingface-hub": "0.36.0",
    "numpy": "2.2.6",
    "safetensors": "0.6.2",
    "transformers": "4.57.6",
}
observed = {name: metadata.version(name) for name in expected}
if observed != expected:
    raise SystemExit(f"pinned dependency versions differ: {observed}")

if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
    raise SystemExit("exactly one CUDA GPU is required")
properties = torch.cuda.get_device_properties(0)
if int(properties.total_memory) < 160 * 1024**3:
    raise SystemExit(
        f"at least 160 GiB VRAM is required; observed {properties.total_memory} bytes"
    )
print(
    {
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "gpu": properties.name,
        "total_memory_bytes": int(properties.total_memory),
    }
)
PY

# This reconstructs every bound source byte against source_inventory.json and
# therefore rejects repository drift without assuming Git ownership or status.
"${PYTHON_BIN}" -m experiments.consciousness_readout_validation.validate_plan \
  "$(dirname "${PLAN_MANIFEST}")"

COMMON_ARGS=(
  --plan-manifest "${PLAN_MANIFEST}"
  --execution-binding "${EXECUTION_BINDING}"
  --artifact-root "${CONSCIOUSNESS_READOUT_VALIDATION_ARTIFACT_ROOT}"
  --volume-id "${CONSCIOUSNESS_READOUT_VALIDATION_VOLUME_ID}"
)
if [[ "${PHASE}" == "ALL" ]]; then
  "${PYTHON_BIN}" -m experiments.consciousness_readout_validation.gpu_runner \
    --all-phases --run-id-prefix "${RUN_ID_PREFIX}" "${COMMON_ARGS[@]}"
else
  "${PYTHON_BIN}" -m experiments.consciousness_readout_validation.gpu_runner \
    --phase "${PHASE}" --run-id "${RUN_ID}" "${COMMON_ARGS[@]}"
fi

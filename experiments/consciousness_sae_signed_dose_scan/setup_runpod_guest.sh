#!/usr/bin/env bash
set -euo pipefail

if [[ "${RUNPOD_VOLUME_ID:-}" != "bv9gb9j32y" ]]; then
  echo "wrong RunPod volume" >&2
  exit 2
fi
if [[ "${RUNPOD_DC_ID:-}" != "US-CA-2" ]]; then
  echo "wrong RunPod data center" >&2
  exit 2
fi
if [[ -z "${RUNPOD_POD_ID:-}" ]]; then
  echo "missing RunPod pod identity" >&2
  exit 2
fi

python3 -m pip uninstall --yes PyGObject >/dev/null 2>&1 || true
python3 -m pip install --disable-pip-version-check --no-cache-dir \
  --requirement experiments/consciousness_sae_signed_dose_scan/requirements-runpod-b200.txt
python3 -m pip check
python3 - <<'PY'
from importlib import metadata

expected = {
    "accelerate": "1.12.0",
    "huggingface-hub": "0.36.0",
    "numpy": "2.2.6",
    "safetensors": "0.8.0",
    "scipy": "1.15.3",
    "tokenizers": "0.22.2",
    "transformers": "4.57.6",
}
observed = {name: metadata.version(name) for name in expected}
if observed != expected:
    raise SystemExit(f"guest dependency versions differ: {observed!r}")
PY

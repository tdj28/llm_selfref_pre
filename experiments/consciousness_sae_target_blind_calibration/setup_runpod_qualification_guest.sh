#!/usr/bin/env bash
set -euo pipefail

# Preserve the exact r3/final-recovery runtime setup, then add only the test
# runner required on disposable source/test qualification hosts.
bash experiments/consciousness_sae_target_blind_calibration/setup_runpod_guest.sh
python3 -m pip install --disable-pip-version-check --no-cache-dir \
  --requirement experiments/consciousness_sae_target_blind_calibration/requirements-runpod-b200-qualification.txt
python3 -m pip check
python3 - <<'PY'
from importlib import metadata

observed = metadata.version("pytest")
if observed != "8.4.2":
    raise SystemExit(f"qualification pytest version differs: {observed!r}")
PY

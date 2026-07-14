#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(
  CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1
  pwd -P
)"
REPO_ROOT="$(
  CDPATH= cd -- "${SCRIPT_DIR}/../.." >/dev/null 2>&1
  pwd -P
)"

case "${REPO_ROOT}" in
  /workspace|/workspace/*)
    echo "bound repository source root must be outside /workspace" >&2
    exit 2
    ;;
esac

case "${1:-}" in
  attest)
    MODULE="experiments.consciousness_readout_validation.guest_attestation"
    ;;
  stage)
    MODULE="experiments.consciousness_readout_validation.stage_public_artifacts"
    ;;
  *)
    echo "usage: run_guest_preflight.sh {attest|stage} [module arguments...]" >&2
    exit 2
    ;;
esac
shift

cd -- "${REPO_ROOT}"
export PYTHONDONTWRITEBYTECODE=1
exec python3 -B -m "${MODULE}" "$@"

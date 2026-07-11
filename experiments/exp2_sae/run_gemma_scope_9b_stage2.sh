#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 4 ]]; then
  echo "usage: $0 STEERING_PID [REPO_ROOT] [RUN_DIR] [PLAN_DIR]" >&2
  exit 2
fi

steering_pid="$1"
repo_root="${2:-/workspace/CONSCIOUS}"
run_dir="${3:-${repo_root}/data/gemma_scope_9b/confirmatory_v1_20260711}"
plan_dir="${4:-${repo_root}/data/gemma_scope_9b/confirmatory_v1_plan_20260711}"
steering_dir="${run_dir}/steering"
judging_dir="${run_dir}/judging"
exploratory_dir="${run_dir}/atlas_exploratory"

export HF_HOME="${HF_HOME:-/workspace/cache/huggingface}"
if [[ -z "${HF_TOKEN:-}" ]]; then
  if [[ ! -r /workspace/.hf_token ]]; then
    echo "HF_TOKEN is unset and /workspace/.hf_token is unavailable" >&2
    exit 1
  fi
  HF_TOKEN="$(tr -d '\r\n' < /workspace/.hf_token)"
  export HF_TOKEN
fi

cd "$repo_root"
while kill -0 "$steering_pid" 2>/dev/null; do
  sleep 30
done

python3 - "$steering_dir" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

steering_dir = Path(sys.argv[1])
complete = json.loads(
    (steering_dir / "steering_complete.json").read_text(encoding="utf-8")
)
rows_path = steering_dir / "steering_generations.jsonl"
rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
digest = hashlib.sha256(rows_path.read_bytes()).hexdigest()
if complete.get("status") != "steering_generation_complete_unjudged":
    raise SystemExit("steering completion status is not the frozen unjudged status")
if complete.get("behavioral_outcomes_inspected") is not False:
    raise SystemExit("steering completion does not preserve behavioral blinding")
if complete.get("n_rows") != 830 or len(rows) != 830:
    raise SystemExit("steering generation does not contain exactly 830 rows")
if len({str(row["trial_id"]) for row in rows}) != 830:
    raise SystemExit("steering generation trial IDs are not unique")
if complete.get("generations_sha256") != digest:
    raise SystemExit("steering generation hash differs from completion metadata")
PY

python3 experiments/exp2_sae/build_gemma_scope_9b_judge_packet.py \
  --baseline "${run_dir}/baseline/baseline_generations.jsonl" \
  --steering "${steering_dir}/steering_generations.jsonl" \
  --outdir "$judging_dir"
touch /workspace/gemma_packet.ready

python3 experiments/exp2_sae/judge_gemma_scope_9b_local.py \
  --packet-dir "$judging_dir" \
  --out "${judging_dir}/local_gemma_judgments.jsonl" \
  > /workspace/gemma_local_judge.log 2>&1

python3 experiments/exp2_sae/run_gemma_scope_9b_exploratory_atlas.py \
  --plan-dir "$plan_dir" \
  --confirmatory-atlas "${run_dir}/atlas" \
  --outdir "$exploratory_dir" \
  > /workspace/gemma_exploratory_atlas.log 2>&1

python3 experiments/exp2_sae/analyze_gemma_scope_cross_layer.py \
  "$exploratory_dir" \
  > /workspace/gemma_exploratory_cross_layer.log 2>&1

find "$steering_dir" "$judging_dir" "$exploratory_dir" \
  -type f -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  > /workspace/gemma_stage2.sha256
touch /workspace/gemma_stage2.complete

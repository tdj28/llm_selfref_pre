#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 5 ]]; then
  echo "usage: $0 SSH_HOST SSH_PORT SSH_KEY REMOTE_RUN_DIR LOCAL_RUN_DIR" >&2
  exit 2
fi

ssh_host="$1"
ssh_port="$2"
ssh_key="$3"
remote_run_dir="$4"
local_run_dir="$5"
repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
local_judging_dir="${local_run_dir}/judging"
remote_judging_dir="${remote_run_dir}/judging"

while ! ssh -i "$ssh_key" -p "$ssh_port" -o StrictHostKeyChecking=yes \
  "$ssh_host" 'test -e /workspace/gemma_packet.ready'; do
  sleep 30
done

mkdir -p "$local_judging_dir"
for name in \
  blinded_judge_packet.jsonl \
  direct_answer_labels.jsonl \
  JUDGE_PACKET_MANIFEST.json; do
  scp -i "$ssh_key" -P "$ssh_port" -o StrictHostKeyChecking=yes \
    "${ssh_host}:${remote_judging_dir}/${name}" \
    "${local_judging_dir}/${name}"
done

python3 - "$local_judging_dir" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

judging_dir = Path(sys.argv[1])
manifest = json.loads(
    (judging_dir / "JUDGE_PACKET_MANIFEST.json").read_text(encoding="utf-8")
)
packet_path = judging_dir / "blinded_judge_packet.jsonl"
direct_path = judging_dir / "direct_answer_labels.jsonl"
packet = [json.loads(line) for line in packet_path.read_text(encoding="utf-8").splitlines()]
direct = [json.loads(line) for line in direct_path.read_text(encoding="utf-8").splitlines()]
if manifest.get("status") != "complete":
    raise SystemExit("judge packet manifest is incomplete")
if len(packet) != 1010 or len(direct) != 1010:
    raise SystemExit("judge packet or direct-label row count is not 1,010")
if len({str(row["trial_id"]) for row in packet}) != 1010:
    raise SystemExit("judge packet trial IDs are not unique")
if {str(row["trial_id"]) for row in packet} != {
    str(row["trial_id"]) for row in direct
}:
    raise SystemExit("judge packet and direct-label trial IDs differ")
if manifest.get("packet_sha256") != hashlib.sha256(packet_path.read_bytes()).hexdigest():
    raise SystemExit("judge packet hash differs from manifest")
if manifest.get("direct_labels_sha256") != hashlib.sha256(direct_path.read_bytes()).hexdigest():
    raise SystemExit("direct-label hash differs from manifest")
PY

cd "$repo_root"
success=0
for attempt in 1 2 3 4 5; do
  if steering/.venv/bin/python \
    experiments/exp2_sae/judge_gemma_scope_9b_external.py \
    --packet-dir "$local_judging_dir" \
    --out "${local_judging_dir}/external_judgments.jsonl" \
    --max-workers 8 \
    >> "${local_judging_dir}/external_judge.log" 2>&1; then
    success=1
    break
  fi
  sleep $((attempt * 30))
done

if [[ "$success" -ne 1 ]]; then
  echo "external Gemma judging did not complete after five resumable attempts" >&2
  exit 1
fi

python3 - "$local_judging_dir" <<'PY'
import json
import sys
from pathlib import Path

judging_dir = Path(sys.argv[1])
rows = [
    json.loads(line)
    for line in (judging_dir / "external_judgments.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
]
manifest = json.loads(
    (judging_dir / "external_judgments.manifest.json").read_text(encoding="utf-8")
)
if manifest.get("status") != "complete" or len(rows) != 2020:
    raise SystemExit("external Gemma judge panel is incomplete")
if len({str(row["judgment_id"]) for row in rows}) != 2020:
    raise SystemExit("external Gemma judgment IDs are not unique")
PY

echo "external_controller=complete"

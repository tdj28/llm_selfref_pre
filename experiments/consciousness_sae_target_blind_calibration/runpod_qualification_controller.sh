#!/usr/bin/env bash
set -euo pipefail

FREEZE=${1:?missing exact code-freeze commit}
POD_ID=${2:?missing exact owned pod ID}
EXPECTED_CREATED_AT=${3:?missing host-created timestamp}
EXPECTED_TEST_COUNT=${4:-231}

[[ "$FREEZE" =~ ^[0-9a-f]{40}$ ]]
[[ "$POD_ID" =~ ^[a-z0-9]{5,64}$ ]]
[[ "$EXPECTED_CREATED_AT" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]
[[ "$EXPECTED_TEST_COUNT" == 231 ]]

ROOT="/root/q14-${FREEZE:0:7}"
ACTIVE="$ROOT/checkout"
DEPS="$ROOT/dependencies"
BOOTSTRAP="$ROOT/bootstrap"
MANIFEST="$BOOTSTRAP/APPROVED_IMPORT_ROOTS.json"
OWNERSHIP="$ROOT/evidence/TARGET_QUALIFICATION_OWNERSHIP.json"
HOST_WRAPPER="$ROOT/run_qualification_pipe_logged.sh"
PYTHON=/usr/bin/python3.11
ARCHIVE_PARENT=/workspace/consciousness_sae_target_blind_calibration/consciousness_sae_target_blind_calibration_v2/qualification_archives
ARCHIVE="$ARCHIVE_PARENT/v9-b22-c14-target-${POD_ID}-${FREEZE:0:7}"
ARCHIVE_PARTIAL="${ARCHIVE}.partial"
ARCHIVE_PUBLISHED=0

stage() {
  printf '%s %s\n' "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

copy_if_file() {
  local source=$1 destination=$2
  if [[ -f "$source" ]]; then
    install -D -m 600 "$source" "$destination"
  fi
}

publish_support_archive() {
  local status=$1 exit_code=$2
  test ! -e "$ARCHIVE"
  test ! -e "$ARCHIVE_PARTIAL"
  install -d -m 700 \
    "$ARCHIVE_PARTIAL/bootstrap" \
    "$ARCHIVE_PARTIAL/controller" \
    "$ARCHIVE_PARTIAL/guest_preflight" \
    "$ARCHIVE_PARTIAL/probe" \
    "$ARCHIVE_PARTIAL/test"

  "$PYTHON" -B - "$ARCHIVE_PARTIAL/QUALIFICATION_STATUS.json" \
    "$status" "$exit_code" "$FREEZE" "$POD_ID" "$ROOT" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "schema_version": 1,
    "status": sys.argv[2],
    "exit_code": int(sys.argv[3]),
    "code_freeze_commit": sys.argv[4],
    "pod_id": sys.argv[5],
    "remote_qualification_root": sys.argv[6],
    "archived_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
}
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
PY

  copy_if_file "$MANIFEST" "$ARCHIVE_PARTIAL/bootstrap/APPROVED_IMPORT_ROOTS.json"
  copy_if_file "$ROOT/guest_preflight/GUEST_PREFLIGHT.json" "$ARCHIVE_PARTIAL/guest_preflight/GUEST_PREFLIGHT.json"
  copy_if_file "$ROOT/setup.log" "$ARCHIVE_PARTIAL/setup.log"
  copy_if_file "$ROOT/remote.stdout" "$ARCHIVE_PARTIAL/remote.stdout"
  copy_if_file "$ROOT/remote.stderr" "$ARCHIVE_PARTIAL/remote.stderr"
  copy_if_file "$ROOT/run_target_qualification.sh" "$ARCHIVE_PARTIAL/controller/run_target_qualification.sh"
  copy_if_file "$HOST_WRAPPER" "$ARCHIVE_PARTIAL/controller/run_qualification_pipe_logged.sh"
  if [[ -d "$ROOT/controller" ]]; then
    while IFS= read -r -d '' source; do
      copy_if_file "$source" "$ARCHIVE_PARTIAL/controller/$(basename "$source")"
    done < <(find "$ROOT/controller" -maxdepth 1 -type f -name '*.json' -print0)
  fi
  copy_if_file "$ROOT/probe/output/TARGET_QUALIFICATION_LANDLOCK_ENFORCEMENT.json" \
    "$ARCHIVE_PARTIAL/probe/TARGET_QUALIFICATION_LANDLOCK_ENFORCEMENT.json"
  copy_if_file "$ROOT/probe/output/TARGET_QUALIFICATION_LANDLOCK_CUDA_PREFLIGHT.json" \
    "$ARCHIVE_PARTIAL/probe/TARGET_QUALIFICATION_LANDLOCK_CUDA_PREFLIGHT.json"
  if [[ -d "$ROOT/test" ]]; then
    while IFS= read -r -d '' source; do
      copy_if_file "$source" "$ARCHIVE_PARTIAL/test/$(basename "$source")"
    done < <(find "$ROOT/test" -maxdepth 1 -type f -print0)
  fi
  (
    cd "$ARCHIVE_PARTIAL"
    find . -type f ! -name SHA256SUMS -print0 |
      LC_ALL=C sort -z |
      xargs -0 sha256sum >SHA256SUMS
    sha256sum -c SHA256SUMS
  )
  mv "$ARCHIVE_PARTIAL" "$ARCHIVE"
  ARCHIVE_PUBLISHED=1
}

on_exit() {
  local rc=$?
  trap - EXIT
  if ((ARCHIVE_PUBLISHED == 0)); then
    set +e
    publish_support_archive failed "$rc"
    set -e
  fi
  exit "$rc"
}
trap on_exit EXIT

stage TARGET_QUALIFICATION_START
"$PYTHON" -B - "$ROOT/probe/canary/output/.s" <<'PY'
import os
import sys

path = sys.argv[1]
assert path.startswith("/root/q14-")
assert len(os.fsencode(path)) <= 91
assert len(os.fsencode(path)) <= 107 - 16
PY
test -d "$ROOT"
test -f "$OWNERSHIP"
test -f "$ROOT/run_target_qualification.sh"
test -f "$HOST_WRAPPER"
test ! -e "$ACTIVE"
test ! -e "$DEPS"
test ! -e "$BOOTSTRAP"
test ! -e "$ROOT/guest_preflight"
test ! -e "$ROOT/probe"
test ! -e "$ROOT/test"
test ! -e "$ARCHIVE"
test ! -e "$ARCHIVE_PARTIAL"

# Bind the controller arguments to the self-hashed ownership receipt and the
# provider-initialized PID 1 environment before setup or dependency mutation.
"$PYTHON" -B - "$OWNERSHIP" "$POD_ID" "$EXPECTED_CREATED_AT" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

receipt = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
claimed = receipt.get("receipt_sha256")
core = dict(receipt)
core.pop("receipt_sha256", None)
observed_hash = hashlib.sha256(
    json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
).hexdigest()
assert claimed == observed_hash
assert receipt["pod_id"] == sys.argv[2]
assert receipt["created_at"] == sys.argv[3]
assert receipt["network_volume_id"] == "bv9gb9j32y"
assert receipt["data_center_id"] == "US-CA-2"
assert receipt["gpu_type"] == "NVIDIA B200"
assert receipt["gpu_count"] == 1
assert receipt["status"] == "owned_running_isolated"

payload = Path("/proc/1/environ").read_bytes()
assert payload and len(payload) <= 1024 * 1024 and payload.endswith(b"\0")
entries = payload[:-1].split(b"\0")
assert 0 < len(entries) <= 16_384
wanted = {"RUNPOD_POD_ID", "RUNPOD_VOLUME_ID", "RUNPOD_DC_ID"}
observed = {}
for entry in entries:
    assert entry and len(entry) <= 64 * 1024 and b"=" in entry
    name, value = entry.split(b"=", 1)
    try:
        decoded_name = name.decode("ascii")
    except UnicodeDecodeError:
        continue
    if decoded_name not in wanted:
        continue
    assert decoded_name not in observed and len(value) <= 256
    observed[decoded_name] = value.decode("utf-8")
assert observed == {
    "RUNPOD_POD_ID": sys.argv[2],
    "RUNPOD_VOLUME_ID": "bv9gb9j32y",
    "RUNPOD_DC_ID": "US-CA-2",
}
PY

export RUNPOD_POD_ID="$POD_ID"
export RUNPOD_VOLUME_ID=bv9gb9j32y
export RUNPOD_DC_ID=US-CA-2

stage CHECKOUT_START
git init -q "$ACTIVE"
git -C "$ACTIVE" remote add origin https://github.com/tdj28/llm_selfref_pre.git
# This suite verifies that immutable historical review commits are ancestors of
# the current freeze, so the qualification checkout must include branch history.
git -C "$ACTIVE" fetch --no-tags origin refs/heads/feat/sae-changepoint
git -C "$ACTIVE" checkout -q --detach FETCH_HEAD
test "$(git -C "$ACTIVE" rev-parse HEAD)" = "$FREEZE"
test -z "$(git -C "$ACTIVE" status --porcelain=v1 --untracked-files=all)"
stage CHECKOUT_COMPLETE

stage GUEST_PREFLIGHT_START
cd "$ACTIVE"
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -B -m \
  experiments.consciousness_sae_realization_validation.runpod_preflight \
  guest \
  --ownership-receipt "$OWNERSHIP" \
  --receipt-dir "$ROOT/guest_preflight"
"$PYTHON" -B - "$ROOT/guest_preflight/GUEST_PREFLIGHT.json" "$POD_ID" <<'PY'
import json
import sys
from pathlib import Path

receipt = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert receipt["status"] == "pass"
assert receipt["identity_source"] == "provider_pid1_environment"
assert receipt["observed_pod_id"] == sys.argv[2]
assert receipt["observed_volume_id"] == "bv9gb9j32y"
assert receipt["observed_data_center_id"] == "US-CA-2"
assert receipt["model_forward_count"] == 0
assert receipt["target_prompt_render_count"] == 0
assert receipt["prior_outcome_inputs"] == []
PY
stage GUEST_PREFLIGHT_COMPLETE

stage SETUP_START
cd "$ACTIVE"
bash experiments/consciousness_sae_target_blind_calibration/setup_runpod_qualification_guest.sh \
  >"$ROOT/setup.log" 2>&1
stage SETUP_COMPLETE

stage DEPENDENCY_STAGING_START
install -d -m 700 "$DEPS/python3.11" "$DEPS/system_dist_packages" "$BOOTSTRAP"
cp -rL --preserve=mode,timestamps /usr/lib/python3.11/. "$DEPS/python3.11/"
cp -rL --preserve=mode,timestamps /usr/lib/python3/dist-packages/. "$DEPS/system_dist_packages/"
stage DEPENDENCY_STAGING_COMPLETE

stage ROOT_MANIFEST_START
MANIFEST_SHA=$(
  cd "$ACTIVE"
  PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -B - \
    "$ACTIVE" "$DEPS" "$MANIFEST" <<'PY'
import sys
from pathlib import Path
from experiments.consciousness_sae_target_blind_calibration import confined_bootstrap as cb

active = Path(sys.argv[1]).resolve()
deps = Path(sys.argv[2]).resolve()
destination = Path(sys.argv[3]).resolve()
manifest = cb.build_roots_manifest(
    python_executable=Path("/usr/bin/python3.11"),
    active_root=active,
    dependency_roots=(
        ("python_stdlib", deps / "python3.11"),
        ("system_dist_packages", deps / "system_dist_packages"),
        ("local_dist_packages", Path("/usr/local/lib/python3.11/dist-packages")),
    ),
    sys_path=(
        active,
        deps / "python3.11",
        deps / "python3.11/lib-dynload",
        Path("/usr/local/lib/python3.11/dist-packages"),
        deps / "system_dist_packages",
    ),
)
print(cb.write_roots_manifest_exclusive(destination, manifest))
PY
)
[[ "$MANIFEST_SHA" =~ ^[0-9a-f]{64}$ ]]
stage ROOT_MANIFEST_COMPLETE

stage LANDLOCK_CUDA_PROBE_START
OUT="$ROOT/probe/output"
CANARY_PROTECTED="$ROOT/probe/canary/protected"
CANARY_OUTPUT="$ROOT/probe/canary/output"
LANDLOCK="$OUT/TARGET_QUALIFICATION_LANDLOCK_ENFORCEMENT.json"
CUDA="$OUT/TARGET_QUALIFICATION_LANDLOCK_CUDA_PREFLIGHT.json"
install -d -m 700 "$OUT" "$CANARY_PROTECTED" "$CANARY_OUTPUT"
install -m 600 /dev/null "$CANARY_PROTECTED/seed.txt"

# Docker/RunPod can misreport bind-mounted device dirent types to find(1).
# Enumerate only frozen NVIDIA globs, validate the exact regex, then use test -c.
shopt -s nullglob
DEVICE_CANDIDATES=(
  /dev/nvidia[0-9]*
  /dev/nvidiactl
  /dev/nvidia-uvm
  /dev/nvidia-uvm-tools
  /dev/nvidia-caps/nvidia-cap[0-9]*
)
shopt -u nullglob
DEVICES=()
for candidate in "${DEVICE_CANDIDATES[@]}"; do
  if [[ "$candidate" =~ ^/dev/nvidia[0-9]+$ ||
        "$candidate" =~ ^/dev/nvidiactl$ ||
        "$candidate" =~ ^/dev/nvidia-uvm$ ||
        "$candidate" =~ ^/dev/nvidia-uvm-tools$ ||
        "$candidate" =~ ^/dev/nvidia-caps/nvidia-cap[0-9]+$ ]]; then
    if [[ -c "$candidate" ]]; then
      DEVICES+=("$candidate")
    fi
  else
    printf 'NVIDIA allowlisted glob produced rejected path: %s\n' "$candidate" >&2
    exit 2
  fi
done
((${#DEVICES[@]} > 0))
mapfile -t DEVICES < <(printf '%s\n' "${DEVICES[@]}" | LC_ALL=C sort -u)
((${#DEVICES[@]} > 0))
for device in "${DEVICES[@]}"; do
  test -c "$device"
done

CHILD=(
  "$PYTHON" -B -E -s -S
  "$ACTIVE/experiments/consciousness_sae_target_blind_calibration/confined_bootstrap.py"
  --mode preflight-child
  --active-root "$ACTIVE"
  --roots-manifest "$MANIFEST"
  --roots-manifest-sha256 "$MANIFEST_SHA"
  --
  --python-executable "$PYTHON"
  --active-root "$ACTIVE"
  --roots-manifest "$MANIFEST"
  --roots-manifest-sha256 "$MANIFEST_SHA"
  --landlock-receipt "$LANDLOCK"
  --output-root "$OUT"
  --canary-protected-root "$CANARY_PROTECTED"
  --canary-output-root "$CANARY_OUTPUT"
  --closure-scope source_test_qualification
  --qualification-ownership "$OWNERSHIP"
)
for device in "${DEVICES[@]}"; do CHILD+=(--device-file "$device"); done
CHILD+=(--output "$CUDA")

LAUNCH=(
  "$PYTHON" -B -E -s -S
  "$ACTIVE/experiments/consciousness_sae_target_blind_calibration/landlock_launcher.py"
  --purpose preauthorization_probe
  --output-root "$OUT"
  --canary-protected-root "$CANARY_PROTECTED"
  --canary-output-root "$CANARY_OUTPUT"
  --protected-root "$ACTIVE"
  --protected-root "$BOOTSTRAP"
  --protected-root "$DEPS/python3.11"
  --protected-root "$DEPS/system_dist_packages"
  --protected-root /usr/local/lib/python3.11/dist-packages
  --protected-file "$ACTIVE/experiments/consciousness_sae_target_blind_calibration/confined_bootstrap.py"
  --protected-file "$MANIFEST"
  --protected-file "$OWNERSHIP"
  --protected-file "$CANARY_PROTECTED/seed.txt"
)
for device in "${DEVICES[@]}"; do LAUNCH+=(--device-file "$device"); done
LAUNCH+=(
  --receipt "$LANDLOCK"
  --source-sha256 "$(sha256sum "$ACTIVE/experiments/consciousness_sae_target_blind_calibration/landlock_launcher.py" | awk '{print $1}')"
  -- "${CHILD[@]}"
)

cd "$ACTIVE"
env -i \
  PATH=/usr/bin:/bin LANG=C LC_ALL=C \
  PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
  CUBLAS_WORKSPACE_CONFIG=:4096:8 \
  CUDA_CACHE_DISABLE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  HF_DATASETS_OFFLINE=1 TOKENIZERS_PARALLELISM=false \
  HOME="$OUT" TMPDIR="$OUT" HF_HOME="$OUT" TRANSFORMERS_CACHE="$OUT" \
  XDG_CACHE_HOME="$OUT" TORCH_HOME="$OUT" PIP_CACHE_DIR="$OUT" \
  NUMBA_CACHE_DIR="$OUT" CUDA_CACHE_PATH="$OUT" TRITON_CACHE_DIR="$OUT" \
  TORCHINDUCTOR_CACHE_DIR="$OUT" PYTHONPYCACHEPREFIX="$OUT" \
  RUNPOD_POD_ID="$POD_ID" RUNPOD_VOLUME_ID=bv9gb9j32y RUNPOD_DC_ID=US-CA-2 \
  "${LAUNCH[@]}"
test -s "$LANDLOCK"
test -s "$CUDA"
stage LANDLOCK_CUDA_PROBE_COMPLETE

stage TARGET_TEST_START
TEST="$ROOT/test"
install -d -m 700 "$TEST"
cp "$OWNERSHIP" "$TEST/TARGET_QUALIFICATION_OWNERSHIP.json"
cp "$LANDLOCK" "$TEST/TARGET_QUALIFICATION_LANDLOCK_ENFORCEMENT.json"
cp "$CUDA" "$TEST/TARGET_QUALIFICATION_LANDLOCK_CUDA_PREFLIGHT.json"

cd "$ACTIVE"
PYTHONDONTWRITEBYTECODE=1 \
CUBLAS_WORKSPACE_CONFIG=:4096:8 \
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
"$PYTHON" -B -m \
  experiments.consciousness_sae_target_blind_calibration.audit_recovery \
  test-receipt \
  --kind target_host \
  --code-freeze-commit "$FREEZE" \
  --host-created-at-utc "$EXPECTED_CREATED_AT" \
  --qualification-ownership "$TEST/TARGET_QUALIFICATION_OWNERSHIP.json" \
  --qualification-landlock "$TEST/TARGET_QUALIFICATION_LANDLOCK_ENFORCEMENT.json" \
  --qualification-cuda-preflight "$TEST/TARGET_QUALIFICATION_LANDLOCK_CUDA_PREFLIGHT.json" \
  --output "$TEST/TARGET_HOST_TEST_RECEIPT.json"

"$PYTHON" -B - "$TEST/TARGET_HOST_TEST_RECEIPT.json" "$FREEZE" "$EXPECTED_TEST_COUNT" <<'PY'
import json
import sys
from pathlib import Path

receipt = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
freeze = sys.argv[2]
expected = int(sys.argv[3])
assert expected == 231
assert receipt["status"] == "pass_exact_code_freeze_tests"
assert receipt["code_freeze_commit"] == freeze
assert receipt["observed_git_head_commit"] == freeze
assert receipt["exit_code"] == 0
assert receipt["collected_count"] == expected
assert receipt["passed_count"] == expected
assert receipt["failed_count"] == 0
assert receipt["skipped_count"] == 0
assert receipt["not_run_count"] == 0
assert len(receipt["collected_ids"]) == expected
assert receipt["passed_count"] == receipt["collected_count"]
assert set(receipt["designated_target_ids"]) <= set(receipt["passed_ids"])
assert receipt["qualification_probe"]["cuda_preflight_closure_scope"] == "source_test_qualification"
assert receipt["target_host"]["pod_id"] == receipt["qualification_probe"]["provider"]["pod_id"]
PY

(
  cd "$TEST"
  sha256sum \
    TARGET_HOST_TEST_RECEIPT.json \
    TARGET_QUALIFICATION_OWNERSHIP.json \
    TARGET_QUALIFICATION_LANDLOCK_ENFORCEMENT.json \
    TARGET_QUALIFICATION_LANDLOCK_CUDA_PREFLIGHT.json \
    >TARGET_INPUTS.sha256
  sha256sum -c TARGET_INPUTS.sha256
)
stage TARGET_TEST_COMPLETE

stage SUPPORT_ARCHIVE_START
publish_support_archive pass 0
stage SUPPORT_ARCHIVE_COMPLETE
stage TARGET_QUALIFICATION_COMPLETE

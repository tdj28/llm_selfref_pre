#!/usr/bin/env bash
set -euo pipefail

CODE_FREEZE=${1:?missing C15 code-freeze commit}
REVIEWED_PACKET_COMMIT=${2:?missing E15 reviewed-packet commit}
FINAL_FREEZE=${3:?missing F15 final-freeze commit}
POD_ID=${4:?missing receipt-owned pod id}
EXPECTED_CREATED_AT=${5:?missing provider-created UTC}
ATTEMPT_ID=${6:?missing attempt id}
INPUT_ROOT=${7:?missing staged input root}

for commit in "$CODE_FREEZE" "$REVIEWED_PACKET_COMMIT" "$FINAL_FREEZE"; do
  [[ "$commit" =~ ^[0-9a-f]{40}$ ]]
done
FINAL_SHORT=${FINAL_FREEZE:0:7}
[[ "$POD_ID" =~ ^[a-z0-9]{6,32}$ ]]
[[ "$EXPECTED_CREATED_AT" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]
[[ "$ATTEMPT_ID" =~ ^calv2-r3-audit-recovery-${FINAL_SHORT}-[0-9]{8}T[0-9]{6}Z$ ]]
[[ "$INPUT_ROOT" == /root/final-recovery-inputs-* ]]
for rejected_pod in 9n5f5a82p1gw1e eeo1skjkwjqot5 j7xr357tdlpq3f; do
  [[ "$POD_ID" != "$rejected_pod" ]]
  [[ "$INPUT_ROOT" != *"$rejected_pod"* ]]
done
for rejected_attempt in \
  calv2-r3-audit-recovery-2479ed0-20260715T155035Z \
  calv2-r3-audit-recovery-2479ed0-20260715T165648Z \
  calv2-r3-audit-recovery-497b0f8-20260715T191757Z; do
  [[ "$ATTEMPT_ID" != "$rejected_attempt" ]]
  [[ "$INPUT_ROOT" != *"$rejected_attempt"* ]]
done

REJECTED_B20_AUTHORIZATION_RECEIPT_SHA256=f6d0fa7fdf5b6ec8553fce2fe8df7842dd28f5a63fb5a9674a6358d4af152358
REJECTED_B20_AUTHORIZATION_FILE_SHA256=897a0fe5fac8e898f6367b8115a982a7580c0224843a76e2514589f6277274a7
REJECTED_B22_AUTHORIZATION_RECEIPT_SHA256=8cb249316e406f795150cb55409c6053b8e29c4b510918ea7c539bbb969306d4
REJECTED_B22_AUTHORIZATION_FILE_SHA256=682e5a612e48e196a46ea762fe00ab4de32df1bf070aa72edf64d2639735f5ff

PYTHON=/usr/bin/python3.11
BASE="/root/consciousness_sae_audit_recovery/$ATTEMPT_ID"
SOURCE="$BASE/source"
ACTIVE="$BASE/active"
DEPS="$BASE/dependencies"
FRESH_PREFLIGHT="$BASE/fresh_preflight"
ATTEMPT="/workspace/csae/$ATTEMPT_ID"
RAW=/workspace/consciousness_sae_target_blind_calibration/consciousness_sae_target_blind_calibration_v2/raw/calv2-r3-1a16572-20260715T002344Z
PUBLIC=/workspace/consciousness_readout_validation/consciousness_readout_validation_v1/public_artifacts
PROVENANCE="$ATTEMPT/provenance_repo"
ORIGINAL="$ATTEMPT/evidence/original"
SUPERSEDED="$ATTEMPT/evidence/superseded_recovery_host"
FRESH="$ATTEMPT/evidence/fresh"
TESTS="$ATTEMPT/evidence/tests"
PREFLIGHT="$ATTEMPT/preflight"
PREFLIGHT_OUT="$PREFLIGHT/output"
PREFLIGHT_CANARY_PROTECTED="$PREFLIGHT/canary/protected"
PREFLIGHT_CANARY_OUTPUT="$PREFLIGHT/canary/output"
OUTPUT="$ATTEMPT/output"
CANARY_PROTECTED="$ATTEMPT/landlock_canary/protected"
CANARY_OUTPUT="$ATTEMPT/landlock_canary/output"
MANIFEST="$ATTEMPT/bootstrap/APPROVED_IMPORT_ROOTS.json"
AUTH="$ATTEMPT/RECOVERY_AUTHORIZATION.json"
PLAN_REL=data/consciousness_sae_target_blind_calibration/calibration_v2_plan_20260714_r3
V10_INPUT_REL=docs/consciousness_sae_target_blind_calibration/reviews/audit_recovery_landlock_gpt_pro_v10_inputs
V9_CONDITIONAL_ADJUDICATION_REL=docs/consciousness_sae_target_blind_calibration/reviews/AUDIT_RECOVERY_LANDLOCK_GPT_PRO_V9_ADJUDICATION.json

stage() {
  printf '%s %s\n' "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

stage FINAL_RECOVERY_CONTROLLER_START
test -x "$PYTHON"
test -d "$INPUT_ROOT/original"
test -d "$INPUT_ROOT/superseded"
test -f "$INPUT_ROOT/fresh/OWNERSHIP.json"
test ! -e "$BASE"
test ! -e "$ATTEMPT"
test -d "$RAW"
test -f "$RAW/RUN_COMPLETE.json"
test -d "$PUBLIC"
test -f "$PUBLIC/jlens/Llama-3.3-70B-Instruct_jacobian_lens.pt"

install -d -m 700 "$BASE"

stage SOURCE_CHECKOUT_START
git init -q "$SOURCE"
git -C "$SOURCE" remote add origin https://github.com/tdj28/llm_selfref_pre.git
git -C "$SOURCE" fetch --no-tags origin refs/heads/feat/sae-changepoint:refs/remotes/origin/feat/sae-changepoint
git -C "$SOURCE" checkout -q -b feat/sae-changepoint refs/remotes/origin/feat/sae-changepoint
git -C "$SOURCE" branch --set-upstream-to=origin/feat/sae-changepoint feat/sae-changepoint >/dev/null
test "$(git -C "$SOURCE" rev-parse HEAD)" = "$FINAL_FREEZE"
for commit in "$CODE_FREEZE" "$REVIEWED_PACKET_COMMIT" "$FINAL_FREEZE"; do
  test "$(git -C "$SOURCE" rev-parse --verify "${commit}^{commit}")" = "$commit"
done
git -C "$SOURCE" merge-base --is-ancestor "$CODE_FREEZE" "$REVIEWED_PACKET_COMMIT"
git -C "$SOURCE" merge-base --is-ancestor "$REVIEWED_PACKET_COMMIT" "$FINAL_FREEZE"
git -C "$SOURCE" diff --quiet "$CODE_FREEZE" "$FINAL_FREEZE" -- experiments tests

V10_EXPECTED_PREREVIEW_PATHS=(
  docs/consciousness_sae_target_blind_calibration/reviews/audit_recovery_landlock_gpt_pro_v10_inputs/LOCAL_TEST_RECEIPT.json
  docs/consciousness_sae_target_blind_calibration/reviews/audit_recovery_landlock_gpt_pro_v10_inputs/TARGET_HOST_TEST_RECEIPT.json
  docs/consciousness_sae_target_blind_calibration/reviews/audit_recovery_landlock_gpt_pro_v10_inputs/TARGET_QUALIFICATION_OWNERSHIP.json
  docs/consciousness_sae_target_blind_calibration/reviews/audit_recovery_landlock_gpt_pro_v10_inputs/TARGET_QUALIFICATION_LANDLOCK_ENFORCEMENT.json
  docs/consciousness_sae_target_blind_calibration/reviews/audit_recovery_landlock_gpt_pro_v10_inputs/TARGET_QUALIFICATION_LANDLOCK_CUDA_PREFLIGHT.json
  docs/consciousness_sae_target_blind_calibration/reviews/audit_recovery_landlock_gpt_pro_v10_inputs/V10_EVIDENCE_SUMMARY.json
)
V10_EXPECTED_POSTREVIEW_PATHS=(
  docs/consciousness_sae_target_blind_calibration/reviews/AUDIT_RECOVERY_LANDLOCK_GPT_PRO_V10_ADJUDICATION.json
  docs/consciousness_sae_target_blind_calibration/reviews/AUDIT_RECOVERY_LANDLOCK_GPT_PRO_V10_ADJUDICATION.md
  docs/consciousness_sae_target_blind_calibration/reviews/audit_recovery_landlock_gpt_pro_v10_completed/request_payload.json
  docs/consciousness_sae_target_blind_calibration/reviews/audit_recovery_landlock_gpt_pro_v10_completed/response.json
  docs/consciousness_sae_target_blind_calibration/reviews/audit_recovery_landlock_gpt_pro_v10_completed/review.md
  docs/consciousness_sae_target_blind_calibration/reviews/audit_recovery_landlock_gpt_pro_v10_completed/review_manifest.json
  docs/consciousness_sae_target_blind_calibration/reviews/audit_recovery_landlock_gpt_pro_v10_completed/review_request.md
)
mapfile -t V10_OBSERVED_PREREVIEW_PATHS < <(
  git -C "$SOURCE" diff --name-only "$CODE_FREEZE" "$REVIEWED_PACKET_COMMIT" |
    LC_ALL=C sort
)
mapfile -t V10_EXPECTED_PREREVIEW_PATHS < <(
  printf '%s\n' "${V10_EXPECTED_PREREVIEW_PATHS[@]}" | LC_ALL=C sort
)
((${#V10_OBSERVED_PREREVIEW_PATHS[@]} == ${#V10_EXPECTED_PREREVIEW_PATHS[@]}))
for index in "${!V10_EXPECTED_PREREVIEW_PATHS[@]}"; do
  test "${V10_OBSERVED_PREREVIEW_PATHS[$index]}" = "${V10_EXPECTED_PREREVIEW_PATHS[$index]}"
  test -f "$SOURCE/${V10_EXPECTED_PREREVIEW_PATHS[$index]}"
done
mapfile -t V10_OBSERVED_POSTREVIEW_PATHS < <(
  git -C "$SOURCE" diff --name-only "$REVIEWED_PACKET_COMMIT" "$FINAL_FREEZE" |
    LC_ALL=C sort
)
mapfile -t V10_EXPECTED_POSTREVIEW_PATHS < <(
  printf '%s\n' "${V10_EXPECTED_POSTREVIEW_PATHS[@]}" | LC_ALL=C sort
)
((${#V10_OBSERVED_POSTREVIEW_PATHS[@]} == ${#V10_EXPECTED_POSTREVIEW_PATHS[@]}))
for index in "${!V10_EXPECTED_POSTREVIEW_PATHS[@]}"; do
  test "${V10_OBSERVED_POSTREVIEW_PATHS[$index]}" = "${V10_EXPECTED_POSTREVIEW_PATHS[$index]}"
  test -f "$SOURCE/${V10_EXPECTED_POSTREVIEW_PATHS[$index]}"
done
test -d "$SOURCE/$V10_INPUT_REL"
test -f "$SOURCE/$V9_CONDITIONAL_ADJUDICATION_REL"
"$PYTHON" -B - "$SOURCE/$V9_CONDITIONAL_ADJUDICATION_REL" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
raw = path.read_bytes()
assert hashlib.sha256(raw).hexdigest() == "0d3e928d3d4221917e43dcce29fd51ac028d46c9035a4b339dcd378f79225643"
value = json.loads(raw)
assert value["artifact_type"] == "completed_conditional_provider_review_v9_adjudication"
assert value["final_decision"] == "NOT_READY_TO_EXECUTE"
assert value["receipt_sha256"] == "fb4f4c2b88580c2e57c3a477de3ba43b527d382e28e97cb1b06dbc323430ba6a"
PY
test -z "$(git -C "$SOURCE" status --porcelain=v1 --untracked-files=all)"
stage SOURCE_CHECKOUT_COMPLETE

export RUNPOD_POD_ID="$POD_ID"
export RUNPOD_VOLUME_ID=bv9gb9j32y
export RUNPOD_DC_ID=US-CA-2

stage PROVIDER_IDENTITY_CHECK_START
"$PYTHON" -B - "$INPUT_ROOT/fresh/OWNERSHIP.json" "$POD_ID" "$EXPECTED_CREATED_AT" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

receipt = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
core = dict(receipt)
claimed = core.pop("receipt_sha256")
observed = hashlib.sha256(
    json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
).hexdigest()
assert claimed == observed
assert receipt["pod_id"] == sys.argv[2]
assert receipt["created_at"] == sys.argv[3]
assert receipt["network_volume_id"] == "bv9gb9j32y"
assert receipt["data_center_id"] == "US-CA-2"
assert receipt["gpu_type"] == "NVIDIA B200"
assert receipt["gpu_count"] == 1
assert receipt["status"] == "owned_running_isolated"

payload = Path("/proc/1/environ").read_bytes()
assert payload and payload.endswith(b"\0") and len(payload) <= 1024 * 1024
wanted = {"RUNPOD_POD_ID", "RUNPOD_VOLUME_ID", "RUNPOD_DC_ID"}
found = {}
for entry in payload[:-1].split(b"\0"):
    if not entry or b"=" not in entry:
        continue
    key, value = entry.split(b"=", 1)
    try:
        key_text = key.decode("ascii")
    except UnicodeDecodeError:
        continue
    if key_text in wanted:
        assert key_text not in found
        found[key_text] = value.decode("utf-8")
assert found == {
    "RUNPOD_POD_ID": sys.argv[2],
    "RUNPOD_VOLUME_ID": "bv9gb9j32y",
    "RUNPOD_DC_ID": "US-CA-2",
}
PY
stage PROVIDER_IDENTITY_CHECK_COMPLETE

stage ACTIVE_AND_PROVENANCE_STAGING_START
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -B - \
  "$SOURCE" "$ACTIVE" "$PROVENANCE" "$FINAL_FREEZE" <<'PY'
import hashlib
import os
import shutil
import stat
import sys
from pathlib import Path

source = Path(sys.argv[1]).resolve(strict=True)
active = Path(sys.argv[2]).absolute()
provenance = Path(sys.argv[3]).absolute()
final_freeze = sys.argv[4]
sys.path.insert(0, source.as_posix())
from experiments.consciousness_sae_target_blind_calibration import audit_recovery as ar, protocol

assert ar._git_head() == final_freeze
plan, provenance_paths, provenance_rows = ar._validate_pre_gpu_issue_inputs(
    source / protocol.CANONICAL_PLAN_RELATIVE_PATH
)
assert len(provenance_paths) == len(provenance_rows) == 41
assert protocol.canonical_sha256(provenance_rows) == ar.HISTORICAL_PROVENANCE_INVENTORY_SHA256

def copy_unique(relative: str, destination_root: Path) -> None:
    src = source / relative
    dst = destination_root / relative
    assert src.is_file() and not src.is_symlink()
    dst.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with src.open("rb") as reader, dst.open("xb") as writer:
        shutil.copyfileobj(reader, writer, 8 * 1024 * 1024)
    os.chmod(dst, 0o600)
    assert dst.stat().st_nlink == 1

for relative in ar.RECOVERY_BOUND_PATHS:
    copy_unique(relative, active)
for relative in provenance_paths:
    copy_unique(relative, provenance)

observed_active = []
for path in active.rglob("*"):
    info = path.lstat()
    if stat.S_ISREG(info.st_mode):
        assert info.st_nlink == 1
        observed_active.append(path.relative_to(active).as_posix())
    else:
        assert stat.S_ISDIR(info.st_mode)
assert sorted(observed_active) == list(ar.RECOVERY_BOUND_PATHS)
for row in ar._closure_records():
    path = active / row["path"]
    assert path.stat().st_size == row["bytes"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
ar._validate_provenance_tree(provenance, provenance_rows)
print(f"ACTIVE_FILES={len(observed_active)}")
print(f"PROVENANCE_FILES={len(provenance_rows)}")
PY
stage ACTIVE_AND_PROVENANCE_STAGING_COMPLETE

stage HISTORICAL_AND_TEST_EVIDENCE_STAGING_START
install -D -m 600 "$INPUT_ROOT/original/RUN_COMPLETE.json" "$ORIGINAL/RUN_COMPLETE.json"
install -D -m 600 "$INPUT_ROOT/original/REMOTE_RAW_SHA256SUMS.txt" "$ORIGINAL/REMOTE_RAW_SHA256SUMS.txt"
install -D -m 600 "$INPUT_ROOT/original/REMOTE_RAW_INVENTORY.txt" "$ORIGINAL/REMOTE_RAW_INVENTORY.txt"
install -D -m 600 "$INPUT_ROOT/original/calibration_audit_1a16572.log" "$ORIGINAL/calibration_audit_1a16572.log"
install -D -m 600 "$INPUT_ROOT/original/OWNERSHIP.json" "$ORIGINAL/OWNERSHIP.json"
install -D -m 600 "$INPUT_ROOT/original/GUEST_PREFLIGHT.json" "$ORIGINAL/GUEST_PREFLIGHT.json"
install -D -m 600 "$INPUT_ROOT/original/CACHE_PREFLIGHT.json" "$ORIGINAL/CACHE_PREFLIGHT.json"
install -D -m 600 "$INPUT_ROOT/original/CALIBRATION_AUTHORIZATION.json" "$ORIGINAL/CALIBRATION_AUTHORIZATION.json"
install -D -m 600 "$INPUT_ROOT/original/TERMINATION_AUDIT.json" "$ORIGINAL/TERMINATION_AUDIT.json"
install -D -m 600 "$INPUT_ROOT/original/POSTDELETE_INVENTORY.json" "$ORIGINAL/POSTDELETE_INVENTORY.json"
install -D -m 600 "$INPUT_ROOT/original/frozen_lifecycle/TERMINATION.json" "$ORIGINAL/frozen_lifecycle/TERMINATION.json"

install -D -m 600 "$INPUT_ROOT/superseded/PREEXECUTION_RUNTIME_BLOCK.json" "$SUPERSEDED/PREEXECUTION_RUNTIME_BLOCK.json"
install -D -m 600 "$INPUT_ROOT/superseded/TERMINATION_AUDIT.json" "$SUPERSEDED/TERMINATION_AUDIT.json"
install -D -m 600 "$INPUT_ROOT/superseded/POSTDELETE_INVENTORY.json" "$SUPERSEDED/POSTDELETE_INVENTORY.json"
install -D -m 600 "$INPUT_ROOT/superseded/frozen_lifecycle/TERMINATION.json" "$SUPERSEDED/frozen_lifecycle/TERMINATION.json"

install -D -m 600 "$SOURCE/$V10_INPUT_REL/LOCAL_TEST_RECEIPT.json" "$TESTS/LOCAL_TEST_RECEIPT.json"
install -D -m 600 "$SOURCE/$V10_INPUT_REL/TARGET_HOST_TEST_RECEIPT.json" "$TESTS/TARGET_HOST_TEST_RECEIPT.json"
install -D -m 600 "$SOURCE/$V10_INPUT_REL/TARGET_QUALIFICATION_OWNERSHIP.json" "$TESTS/TARGET_QUALIFICATION_OWNERSHIP.json"
install -D -m 600 "$SOURCE/$V10_INPUT_REL/TARGET_QUALIFICATION_LANDLOCK_ENFORCEMENT.json" "$TESTS/TARGET_QUALIFICATION_LANDLOCK_ENFORCEMENT.json"
install -D -m 600 "$SOURCE/$V10_INPUT_REL/TARGET_QUALIFICATION_LANDLOCK_CUDA_PREFLIGHT.json" "$TESTS/TARGET_QUALIFICATION_LANDLOCK_CUDA_PREFLIGHT.json"
stage HISTORICAL_AND_TEST_EVIDENCE_STAGING_COMPLETE

stage FRESH_GUEST_CACHE_PREFLIGHT_START
cd "$SOURCE"
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -B -m \
  experiments.consciousness_sae_realization_validation.runpod_preflight \
  all \
  --ownership-receipt "$INPUT_ROOT/fresh/OWNERSHIP.json" \
  --receipt-dir "$FRESH_PREFLIGHT"
install -D -m 600 "$INPUT_ROOT/fresh/OWNERSHIP.json" "$FRESH/OWNERSHIP.json"
install -D -m 600 "$FRESH_PREFLIGHT/GUEST_PREFLIGHT.json" "$FRESH/GUEST_PREFLIGHT.json"
install -D -m 600 "$FRESH_PREFLIGHT/CACHE_PREFLIGHT.json" "$FRESH/CACHE_PREFLIGHT.json"
stage FRESH_GUEST_CACHE_PREFLIGHT_COMPLETE

stage CANONICAL_SETUP_START
cd "$ACTIVE"
bash experiments/consciousness_sae_target_blind_calibration/setup_runpod_guest.sh \
  >"$BASE/setup.log" 2>&1
stage CANONICAL_SETUP_COMPLETE

stage DEPENDENCY_STAGING_START
install -d -m 700 "$DEPS/python3.11" "$DEPS/system_dist_packages" "$(dirname "$MANIFEST")"
cp -rL --preserve=mode,timestamps /usr/lib/python3.11/. "$DEPS/python3.11/"
cp -rL --preserve=mode,timestamps /usr/lib/python3/dist-packages/. "$DEPS/system_dist_packages/"
stage DEPENDENCY_STAGING_COMPLETE

stage ROOT_MANIFEST_START
MANIFEST_SHA=$(
  cd "$SOURCE"
  PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -B - "$ACTIVE" "$DEPS" "$MANIFEST" <<'PY'
import sys
from pathlib import Path
from experiments.consciousness_sae_target_blind_calibration import confined_bootstrap as cb

active = Path(sys.argv[1]).resolve(strict=True)
deps = Path(sys.argv[2]).resolve(strict=True)
destination = Path(sys.argv[3]).absolute()
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

stage DEVICE_ENUMERATION_START
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
    printf 'Rejected NVIDIA candidate: %s\n' "$candidate" >&2
    exit 2
  fi
done
mapfile -t DEVICES < <(printf '%s\n' "${DEVICES[@]}" | LC_ALL=C sort -u)
((${#DEVICES[@]} > 0))
for device in "${DEVICES[@]}"; do test -c "$device"; done
printf 'DEVICE_COUNT=%s\n' "${#DEVICES[@]}"
stage DEVICE_ENUMERATION_COMPLETE

stage FINAL_SCOPE_LANDLOCK_CUDA_PREFLIGHT_START
install -d -m 700 "$PREFLIGHT_OUT" "$PREFLIGHT_CANARY_PROTECTED" "$PREFLIGHT_CANARY_OUTPUT"
install -m 600 /dev/null "$PREFLIGHT_CANARY_PROTECTED/seed.txt"
PREFLIGHT_LANDLOCK="$PREFLIGHT_OUT/LANDLOCK_ENFORCEMENT.json"
PREFLIGHT_CUDA="$PREFLIGHT_OUT/LANDLOCK_CUDA_PREFLIGHT.json"

PREFLIGHT_CHILD=(
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
  --landlock-receipt "$PREFLIGHT_LANDLOCK"
  --output-root "$PREFLIGHT_OUT"
  --canary-protected-root "$PREFLIGHT_CANARY_PROTECTED"
  --canary-output-root "$PREFLIGHT_CANARY_OUTPUT"
  --closure-scope final_recovery
)
for device in "${DEVICES[@]}"; do PREFLIGHT_CHILD+=(--device-file "$device"); done
PREFLIGHT_CHILD+=(--output "$PREFLIGHT_CUDA")

PREFLIGHT_LAUNCH=(
  "$PYTHON" -B -E -s -S
  "$ACTIVE/experiments/consciousness_sae_target_blind_calibration/landlock_launcher.py"
  --purpose preauthorization_probe
  --output-root "$PREFLIGHT_OUT"
  --canary-protected-root "$PREFLIGHT_CANARY_PROTECTED"
  --canary-output-root "$PREFLIGHT_CANARY_OUTPUT"
  --protected-root "$PREFLIGHT_CANARY_PROTECTED"
  --protected-root "$ACTIVE"
  --protected-root "$(dirname "$MANIFEST")"
  --protected-root "$DEPS/python3.11"
  --protected-root "$DEPS/system_dist_packages"
  --protected-root /usr/local/lib/python3.11/dist-packages
  --protected-file "$PREFLIGHT_CANARY_PROTECTED/seed.txt"
  --protected-file "$ACTIVE/experiments/consciousness_sae_target_blind_calibration/confined_bootstrap.py"
  --protected-file "$MANIFEST"
)
for device in "${DEVICES[@]}"; do PREFLIGHT_LAUNCH+=(--device-file "$device"); done
PREFLIGHT_LAUNCH+=(
  --receipt "$PREFLIGHT_LANDLOCK"
  --source-sha256 "$(sha256sum "$ACTIVE/experiments/consciousness_sae_target_blind_calibration/landlock_launcher.py" | awk '{print $1}')"
  -- "${PREFLIGHT_CHILD[@]}"
)

cd "$ACTIVE"
env -i \
  PATH=/usr/bin:/bin LANG=C LC_ALL=C \
  PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
  CUBLAS_WORKSPACE_CONFIG=:4096:8 \
  CUDA_CACHE_DISABLE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  HF_DATASETS_OFFLINE=1 TOKENIZERS_PARALLELISM=false \
  HOME="$PREFLIGHT_OUT" TMPDIR="$PREFLIGHT_OUT" HF_HOME="$PREFLIGHT_OUT" \
  TRANSFORMERS_CACHE="$PREFLIGHT_OUT" XDG_CACHE_HOME="$PREFLIGHT_OUT" \
  TORCH_HOME="$PREFLIGHT_OUT" PIP_CACHE_DIR="$PREFLIGHT_OUT" \
  NUMBA_CACHE_DIR="$PREFLIGHT_OUT" CUDA_CACHE_PATH="$PREFLIGHT_OUT" \
  TRITON_CACHE_DIR="$PREFLIGHT_OUT" TORCHINDUCTOR_CACHE_DIR="$PREFLIGHT_OUT" \
  PYTHONPYCACHEPREFIX="$PREFLIGHT_OUT" \
  RUNPOD_POD_ID="$POD_ID" RUNPOD_VOLUME_ID=bv9gb9j32y RUNPOD_DC_ID=US-CA-2 \
  "${PREFLIGHT_LAUNCH[@]}"
test -s "$PREFLIGHT_LANDLOCK"
test -s "$PREFLIGHT_CUDA"
stage FINAL_SCOPE_LANDLOCK_CUDA_PREFLIGHT_COMPLETE

stage FINAL_NAMESPACE_PREPARE
install -d -m 700 "$OUTPUT" "$CANARY_PROTECTED" "$CANARY_OUTPUT"
install -m 600 /dev/null "$CANARY_PROTECTED/seed.txt"
test -z "$(find "$OUTPUT" -mindepth 1 -maxdepth 1 -print -quit)"
stage FINAL_NAMESPACE_READY

DEVICE_ARGS=()
for device in "${DEVICES[@]}"; do DEVICE_ARGS+=(--device-file "$device"); done

stage AUTHENTIC_ISSUE_START
cd "$SOURCE"
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -B - \
  "$ACTIVE/experiments/consciousness_sae_target_blind_calibration/confined_bootstrap.py" \
  issue \
  --plan-dir "$SOURCE/$PLAN_REL" \
  --raw-root "$RAW" \
  --run-complete "$ORIGINAL/RUN_COMPLETE.json" \
  --raw-ledger "$ORIGINAL/REMOTE_RAW_SHA256SUMS.txt" \
  --raw-inventory "$ORIGINAL/REMOTE_RAW_INVENTORY.txt" \
  --failure-log "$ORIGINAL/calibration_audit_1a16572.log" \
  --original-ownership "$ORIGINAL/OWNERSHIP.json" \
  --original-guest "$ORIGINAL/GUEST_PREFLIGHT.json" \
  --original-cache "$ORIGINAL/CACHE_PREFLIGHT.json" \
  --original-authorization "$ORIGINAL/CALIBRATION_AUTHORIZATION.json" \
  --termination-audit "$ORIGINAL/TERMINATION_AUDIT.json" \
  --postdelete-inventory "$ORIGINAL/POSTDELETE_INVENTORY.json" \
  --frozen-termination "$ORIGINAL/frozen_lifecycle/TERMINATION.json" \
  --superseded-runtime-block "$SUPERSEDED/PREEXECUTION_RUNTIME_BLOCK.json" \
  --superseded-termination-audit "$SUPERSEDED/TERMINATION_AUDIT.json" \
  --superseded-frozen-termination "$SUPERSEDED/frozen_lifecycle/TERMINATION.json" \
  --superseded-postdelete-inventory "$SUPERSEDED/POSTDELETE_INVENTORY.json" \
  --fresh-ownership "$FRESH/OWNERSHIP.json" \
  --fresh-guest "$FRESH/GUEST_PREFLIGHT.json" \
  --fresh-cache "$FRESH/CACHE_PREFLIGHT.json" \
  --preflight-landlock "$PREFLIGHT_LANDLOCK" \
  --preflight-probe "$PREFLIGHT_CUDA" \
  --local-test-receipt "$TESTS/LOCAL_TEST_RECEIPT.json" \
  --target-host-test-receipt "$TESTS/TARGET_HOST_TEST_RECEIPT.json" \
  --target-qualification-ownership "$TESTS/TARGET_QUALIFICATION_OWNERSHIP.json" \
  --target-qualification-landlock "$TESTS/TARGET_QUALIFICATION_LANDLOCK_ENFORCEMENT.json" \
  --target-qualification-cuda-preflight "$TESTS/TARGET_QUALIFICATION_LANDLOCK_CUDA_PREFLIGHT.json" \
  --attempt-id "$ATTEMPT_ID" \
  --active-root "$ACTIVE" \
  --python-executable "$PYTHON" \
  --roots-manifest "$MANIFEST" \
  --roots-manifest-sha256 "$MANIFEST_SHA" \
  --provenance-root "$PROVENANCE" \
  --output-root "$OUTPUT" \
  --preflight-output-root "$PREFLIGHT_OUT" \
  --preflight-canary-protected-root "$PREFLIGHT_CANARY_PROTECTED" \
  --preflight-canary-output-root "$PREFLIGHT_CANARY_OUTPUT" \
  --canary-protected-root "$CANARY_PROTECTED" \
  --canary-output-root "$CANARY_OUTPUT" \
  --landlock-receipt "$OUTPUT/LANDLOCK_ENFORCEMENT.json" \
  "${DEVICE_ARGS[@]}" \
  --model-snapshot "$PUBLIC/model_snapshot" \
  --j-lens-path "$PUBLIC/jlens/Llama-3.3-70B-Instruct_jacobian_lens.pt" \
  --artifact-device cuda:0 \
  --audit-out "$OUTPUT/compact/CALIBRATION_AUDIT.json" \
  --summary-out "$OUTPUT/compact/CALIBRATION_SUMMARY.json" \
  --attempt-marker "$OUTPUT/ATTEMPT_STARTED.json" \
  --failure-out "$OUTPUT/FAILURE.json" \
  --hourly-price-usd 6.0 \
  --output "$AUTH" <<'PY'
import hashlib
import importlib.util
import sys
from pathlib import Path

argv = sys.argv[2:]
source_root = Path.cwd().resolve(strict=True)
bootstrap_path = Path(sys.argv[1]).resolve(strict=True)
bootstrap_relative_path = (
    "experiments/consciousness_sae_target_blind_calibration/confined_bootstrap.py"
)
expected_source_entry = (
    source_root
    / "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py"
)
expected_source_bootstrap = source_root / bootstrap_relative_path
expected_bootstrap_sha256 = (
    "616104d2711fd9ae18f5cf930e2dcf497d6b113a718b78b812f4bd7383ab227a"
)
for path, label in (
    (expected_source_bootstrap, "source"),
    (bootstrap_path, "active"),
):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_bootstrap_sha256:
        raise SystemExit(f"{label} confined bootstrap SHA-256 differs")

module_name = (
    "experiments.consciousness_sae_target_blind_calibration.confined_bootstrap"
)
if module_name in sys.modules:
    raise SystemExit("confined bootstrap was imported before active binding")
spec = importlib.util.spec_from_file_location(module_name, bootstrap_path)
if spec is None or spec.loader is None:
    raise SystemExit("could not load active confined bootstrap")
active_bootstrap = importlib.util.module_from_spec(spec)
sys.modules[module_name] = active_bootstrap
spec.loader.exec_module(active_bootstrap)

from experiments.consciousness_sae_target_blind_calibration import audit_recovery

parsed = audit_recovery.build_parser().parse_args(argv)
if parsed.command != "issue":
    raise SystemExit("active-bootstrap bridge only permits issue")
source_entry = Path(audit_recovery.__file__).resolve(strict=True)
expected_active_bootstrap = (
    parsed.active_root.resolve(strict=True) / bootstrap_relative_path
)
if (
    bootstrap_path != expected_active_bootstrap
    or audit_recovery.REPO_ROOT.resolve(strict=True) != source_root
    or audit_recovery.authorize.REPO_ROOT.resolve(strict=True) != source_root
    or audit_recovery.validate_plan.REPO_ROOT.resolve(strict=True) != source_root
    or source_entry != expected_source_entry
    or audit_recovery.confined_bootstrap is not active_bootstrap
    or Path(active_bootstrap.__file__).resolve(strict=True) != bootstrap_path
    or active_bootstrap.BOOTSTRAP_RELATIVE_PATH
    != bootstrap_relative_path
    or active_bootstrap.SCHEMA_VERSION != 1
    or active_bootstrap.MANIFEST_STATUS != "approved_exact_python_import_roots"
):
    raise SystemExit("split-root issue binding differs")

raise SystemExit(audit_recovery.main(argv))
PY
test -s "$AUTH"
stage AUTHENTIC_ISSUE_COMPLETE

readarray -d '' FINAL_CHILD < <(
  "$PYTHON" -B - "$AUTH" <<'PY'
import json
import sys
from pathlib import Path

receipt = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for part in receipt["execution"]["confined_child_argv"]:
    assert isinstance(part, str) and part and "\0" not in part
    sys.stdout.buffer.write(part.encode() + b"\0")
PY
)

read -r AUTH_RECEIPT_SHA PREFLIGHT_RECEIPT_SHA < <(
  "$PYTHON" -B - "$AUTH" "$PREFLIGHT_CUDA" <<'PY'
import json
import sys
from pathlib import Path

auth = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
preflight = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
print(auth["receipt_sha256"], preflight["receipt_sha256"])
PY
)
[[ "$AUTH_RECEIPT_SHA" =~ ^[0-9a-f]{64}$ ]]
[[ "$PREFLIGHT_RECEIPT_SHA" =~ ^[0-9a-f]{64}$ ]]
[[ "$AUTH_RECEIPT_SHA" != "$REJECTED_B20_AUTHORIZATION_RECEIPT_SHA256" ]]
[[ "$AUTH_RECEIPT_SHA" != "$REJECTED_B22_AUTHORIZATION_RECEIPT_SHA256" ]]
AUTH_FILE_SHA=$(sha256sum "$AUTH" | awk '{print $1}')
[[ "$AUTH_FILE_SHA" =~ ^[0-9a-f]{64}$ ]]
[[ "$AUTH_FILE_SHA" != "$REJECTED_B20_AUTHORIZATION_FILE_SHA256" ]]
[[ "$AUTH_FILE_SHA" != "$REJECTED_B22_AUTHORIZATION_FILE_SHA256" ]]

FINAL_LAUNCH=(
  "$PYTHON" -B -E -s -S
  "$ACTIVE/experiments/consciousness_sae_target_blind_calibration/landlock_launcher.py"
  --purpose audit_recovery
  --output-root "$OUTPUT"
  --canary-protected-root "$CANARY_PROTECTED"
  --canary-output-root "$CANARY_OUTPUT"
  --protected-root "$RAW"
  --protected-root "$PROVENANCE"
  --protected-root "$CANARY_PROTECTED"
  --protected-root "$ACTIVE"
  --protected-root "$(dirname "$MANIFEST")"
  --protected-root "$DEPS/python3.11"
  --protected-root "$DEPS/system_dist_packages"
  --protected-root /usr/local/lib/python3.11/dist-packages
  --protected-file "$RAW/RUN_COMPLETE.json"
  --protected-file "$PROVENANCE/$PLAN_REL/plan_manifest.json"
  --protected-file "$AUTH"
  --protected-file "$MANIFEST"
  --protected-file "$ACTIVE/experiments/consciousness_sae_target_blind_calibration/confined_bootstrap.py"
)
for device in "${DEVICES[@]}"; do FINAL_LAUNCH+=(--device-file "$device"); done
FINAL_LAUNCH+=(
  --receipt "$OUTPUT/LANDLOCK_ENFORCEMENT.json"
  --source-sha256 "$(sha256sum "$ACTIVE/experiments/consciousness_sae_target_blind_calibration/landlock_launcher.py" | awk '{print $1}')"
  --authorization-sha256 "$AUTH_RECEIPT_SHA"
  --preflight-receipt-sha256 "$PREFLIGHT_RECEIPT_SHA"
  -- "${FINAL_CHILD[@]}"
)

stage FINAL_CONFINED_EXECUTION_START
cd "$ACTIVE"
env -i \
  PATH=/usr/bin:/bin LANG=C LC_ALL=C \
  PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
  CUBLAS_WORKSPACE_CONFIG=:4096:8 \
  CUDA_CACHE_DISABLE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  HF_DATASETS_OFFLINE=1 TOKENIZERS_PARALLELISM=false \
  HOME="$OUTPUT" TMPDIR="$OUTPUT" HF_HOME="$OUTPUT" \
  TRANSFORMERS_CACHE="$OUTPUT" XDG_CACHE_HOME="$OUTPUT" \
  TORCH_HOME="$OUTPUT" PIP_CACHE_DIR="$OUTPUT" NUMBA_CACHE_DIR="$OUTPUT" \
  CUDA_CACHE_PATH="$OUTPUT" TRITON_CACHE_DIR="$OUTPUT" \
  TORCHINDUCTOR_CACHE_DIR="$OUTPUT" PYTHONPYCACHEPREFIX="$OUTPUT" \
  RUNPOD_POD_ID="$POD_ID" RUNPOD_VOLUME_ID=bv9gb9j32y RUNPOD_DC_ID=US-CA-2 \
  "${FINAL_LAUNCH[@]}"

test -s "$OUTPUT/LANDLOCK_ENFORCEMENT.json"
test -s "$OUTPUT/ATTEMPT_STARTED.json"
test ! -e "$OUTPUT/FAILURE.json"
test -s "$OUTPUT/compact/CALIBRATION_AUDIT.json"
test -s "$OUTPUT/compact/CALIBRATION_SUMMARY.json"
test -s "$OUTPUT/compact/PUBLICATION_COMPLETE.json"
stage FINAL_CONFINED_EXECUTION_COMPLETE
stage FINAL_RECOVERY_CONTROLLER_SUCCESS

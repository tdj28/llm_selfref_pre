#!/usr/bin/env bash
# shellcheck disable=SC2029,SC2329
set -euo pipefail

REPO=${1:?missing repo}
BASE=${2:?missing local base}
RECEIPT_DIR=${3:?missing lifecycle receipt dir}
POD_ID=${4:?missing pod id}
HOST=${5:?missing SSH host}
PORT=${6:?missing SSH port}
KNOWN_HOSTS=${7:?missing known-hosts file}
ATTEMPT_ID=${8:?missing attempt id}
EXPECTED_CREATED_AT=${9:?missing provider-created timestamp}
REMOTE_INPUT=${10:?missing remote input path}
REMOTE_CONTROLLER=${11:?missing remote controller path}
LOCAL_GATE=${12:?missing local hash-and-exec gate}
LOCAL_GATE_VALIDATOR=${13:?missing local launch-receipt validator}
CODE_FREEZE=${14:?missing C14 code-freeze commit}
REVIEWED_PACKET_COMMIT=${15:?missing E14 reviewed-packet commit}
FINAL_FREEZE=${16:?missing F14 final-freeze commit}

for commit in "$CODE_FREEZE" "$REVIEWED_PACKET_COMMIT" "$FINAL_FREEZE"; do
  [[ "$commit" =~ ^[0-9a-f]{40}$ ]]
done
FINAL_SHORT=${FINAL_FREEZE:0:7}
REMOTE_ATTEMPT="/workspace/csae/$ATTEMPT_ID"
REMOTE_BASE="/root/consciousness_sae_audit_recovery/$ATTEMPT_ID"
LOCAL_ATTEMPT="$BASE/retrieved/$ATTEMPT_ID"
DEST="root@$HOST"
EXPECTED_CONTROLLER_SHA=ca9d6606b992507dd9e76afbb9fc219222c858831c93a385de22ac56d4b80006
EXPECTED_GATE_SHA=0f91c891dbcf30d574bf0b12307001936ed49b9c9afb11ff1a70099aad9ea78b
EXPECTED_GATE_VALIDATOR_SHA=b91a132f71390865447de5a664abf8f79c110a50bdfe216d96324d2c2868d09e
REJECTED_B20_AUTHORIZATION_RECEIPT_SHA=f6d0fa7fdf5b6ec8553fce2fe8df7842dd28f5a63fb5a9674a6358d4af152358
REJECTED_B20_AUTHORIZATION_FILE_SHA=897a0fe5fac8e898f6367b8115a982a7580c0224843a76e2514589f6277274a7
REJECTED_B22_AUTHORIZATION_RECEIPT_SHA=8cb249316e406f795150cb55409c6053b8e29c4b510918ea7c539bbb969306d4
REJECTED_B22_AUTHORIZATION_FILE_SHA=682e5a612e48e196a46ea762fe00ab4de32df1bf070aa72edf64d2639735f5ff
REMOTE_GATE_RECEIPT="/root/final-recovery-launch-gate-$POD_ID.json"
LOCAL_GATE_RECEIPT_DIR="$BASE/retrieved/launch-gate"
LOCAL_GATE_RECEIPT="$LOCAL_GATE_RECEIPT_DIR/FINAL_RECOVERY_LAUNCH_GATE.json"
WATCHDOG_ARMED="$BASE/logs/watchdog.armed"
WATCHDOG_PID_FILE="$BASE/logs/watchdog.pid"

[[ "$POD_ID" =~ ^[a-z0-9]{6,32}$ ]]
[[ "$HOST" =~ ^[0-9a-fA-F:.]+$ ]]
[[ "$PORT" =~ ^[0-9]{1,5}$ ]]
((PORT >= 1 && PORT <= 65535))
[[ "$ATTEMPT_ID" =~ ^calv2-r3-audit-recovery-${FINAL_SHORT}-[0-9]{8}T[0-9]{6}Z$ ]]
[[ "$EXPECTED_CREATED_AT" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]
[[ "$REMOTE_INPUT" == /root/final-recovery-inputs-* ]]
[[ "$REMOTE_CONTROLLER" == /root/final_recovery_controller_f11.sh ]]
for rejected_pod in 9n5f5a82p1gw1e eeo1skjkwjqot5 j7xr357tdlpq3f; do
  [[ "$POD_ID" != "$rejected_pod" ]]
  [[ "$REMOTE_INPUT" != *"$rejected_pod"* ]]
done
for rejected_attempt in \
  calv2-r3-audit-recovery-2479ed0-20260715T155035Z \
  calv2-r3-audit-recovery-2479ed0-20260715T165648Z \
  calv2-r3-audit-recovery-497b0f8-20260715T191757Z; do
  [[ "$ATTEMPT_ID" != "$rejected_attempt" ]]
  [[ "$REMOTE_INPUT" != *"$rejected_attempt"* ]]
done
test -d "$REPO"
test -d "$BASE/logs"
test -d "$BASE/retrieved"
test -f "$REPO/.env"
test -f "$RECEIPT_DIR/OWNERSHIP.json"
test -s "$KNOWN_HOSTS"
test -f "$LOCAL_GATE"
test ! -L "$LOCAL_GATE"
test -f "$LOCAL_GATE_VALIDATOR"
test ! -L "$LOCAL_GATE_VALIDATOR"
exec 9<"$LOCAL_GATE"
OBSERVED_GATE_SHA=$(
  /opt/homebrew/bin/python3.11 -I -S -B -c '
import hashlib
import os
import stat
import sys

fd = int(sys.argv[1])

def identity(info):
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_uid,
        info.st_gid,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )

before = os.fstat(fd)
if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
    raise SystemExit("opened gate source is not a singly linked regular file")
if os.lseek(fd, 0, os.SEEK_CUR) != 0:
    raise SystemExit("opened gate source did not begin at offset zero")
digest = hashlib.sha256()
while True:
    chunk = os.read(fd, 1024 * 1024)
    if not chunk:
        break
    digest.update(chunk)
after = os.fstat(fd)
if identity(after) != identity(before):
    raise SystemExit("opened gate source changed while hashing")
os.lseek(fd, 0, os.SEEK_SET)
print(digest.hexdigest())
' 9 9<&9
)
[[ "$OBSERVED_GATE_SHA" == "$EXPECTED_GATE_SHA" ]]
[[ "$(shasum -a 256 "$LOCAL_GATE_VALIDATOR" | awk '{print $1}')" == "$EXPECTED_GATE_VALIDATOR_SHA" ]]
test ! -e "$LOCAL_ATTEMPT"
test ! -e "$LOCAL_GATE_RECEIPT"
test -s "$WATCHDOG_ARMED"
test -s "$WATCHDOG_PID_FILE"
install -d -m 700 "$LOCAL_GATE_RECEIPT_DIR"
WATCHDOG_PID=$(<"$WATCHDOG_PID_FILE")
[[ "$WATCHDOG_PID" =~ ^[0-9]+$ ]]
kill -0 "$WATCHDOG_PID"

# From this point onward every remote/retrieval/lifecycle result is captured
# explicitly so an SSH or copy failure cannot skip exact-pod termination.
set +e

emergency_terminate() {
  trap - EXIT INT TERM
  printf 'SUPERVISOR_EMERGENCY_TERMINATE %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >&2
  /usr/bin/lockf -k -t 360 "$RECEIPT_DIR/termination.lock" \
    /private/tmp/final_recovery_terminate_once.sh \
    "$REPO" "$RECEIPT_DIR" "$POD_ID"
}

on_signal() {
  emergency_terminate
  exit 130
}

on_exit() {
  rc=$?
  trap - EXIT INT TERM
  emergency_terminate
  exit "$rc"
}

trap on_signal INT TERM
trap on_exit EXIT

SSH_OPTS=(
  -T
  -p "$PORT"
  -o BatchMode=yes
  -o ConnectTimeout=15
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=3
  -o StrictHostKeyChecking=yes
  -o UserKnownHostsFile="$KNOWN_HOSTS"
)
SCP_OPTS=(
  -P "$PORT"
  -o BatchMode=yes
  -o ConnectTimeout=15
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=3
  -o StrictHostKeyChecking=yes
  -o UserKnownHostsFile="$KNOWN_HOSTS"
)

printf 'SUPERVISOR_HASH_EXEC_GATE_START controller_sha=%s gate_sha=%s %s\n' \
  "$EXPECTED_CONTROLLER_SHA" "$EXPECTED_GATE_SHA" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ssh "${SSH_OPTS[@]}" "$DEST" \
  /usr/bin/env -i \
  PATH=/usr/bin:/bin \
  HOME=/root \
  LANG=C \
  LC_ALL=C \
  /usr/bin/python3.11 -I -S -B - \
  --code-freeze "$CODE_FREEZE" \
  --reviewed-packet-commit "$REVIEWED_PACKET_COMMIT" \
  --final-freeze "$FINAL_FREEZE" \
  --pod-id "$POD_ID" \
  --created-at "$EXPECTED_CREATED_AT" \
  --attempt-id "$ATTEMPT_ID" \
  --input-root "$REMOTE_INPUT" \
  --gate-source-sha256 "$EXPECTED_GATE_SHA" \
  <&9 \
  2> >(tee "$BASE/logs/controller.stderr" >&2) |
  tee "$BASE/logs/controller.stdout"
REMOTE_PIPESTATUS=("${PIPESTATUS[@]}")
if ((${#REMOTE_PIPESTATUS[@]} == 2)); then
  REMOTE_RC=${REMOTE_PIPESTATUS[0]}
  STDOUT_TEE_RC=${REMOTE_PIPESTATUS[1]}
else
  REMOTE_RC=125
  STDOUT_TEE_RC=125
fi
exec 9<&-
printf 'SUPERVISOR_REMOTE_EXIT rc=%s %s\n' "$REMOTE_RC" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'SUPERVISOR_STDOUT_TEE_EXIT rc=%s %s\n' \
  "$STDOUT_TEE_RC" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

printf 'SUPERVISOR_GATE_RECEIPT_RETRIEVAL_START %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
scp "${SCP_OPTS[@]}" "$DEST:$REMOTE_GATE_RECEIPT" "$LOCAL_GATE_RECEIPT"
GATE_RETRIEVAL_RC=$?
if ((GATE_RETRIEVAL_RC == 0 && STDOUT_TEE_RC == 0)); then
  /opt/homebrew/bin/python3 -B "$LOCAL_GATE_VALIDATOR" \
    --receipt "$LOCAL_GATE_RECEIPT" \
    --ownership-receipt "$RECEIPT_DIR/OWNERSHIP.json" \
    --controller-log "$BASE/logs/controller.stdout" \
    --expected-pod-id "$POD_ID" \
    --expected-created-at "$EXPECTED_CREATED_AT" \
    --expected-attempt-id "$ATTEMPT_ID" \
    --expected-input-root "$REMOTE_INPUT" \
    --expected-gate-source-sha256 "$EXPECTED_GATE_SHA" \
    --expected-code-freeze "$CODE_FREEZE" \
    --expected-reviewed-packet-commit "$REVIEWED_PACKET_COMMIT" \
    --expected-final-freeze "$FINAL_FREEZE" \
    >"$BASE/logs/launch-gate-validation.stdout" \
    2>"$BASE/logs/launch-gate-validation.stderr"
  GATE_VALIDATION_RC=$?
else
  GATE_VALIDATION_RC=1
fi
printf 'SUPERVISOR_GATE_RECEIPT_RETRIEVAL_EXIT copy_rc=%s validation_rc=%s %s\n' \
  "$GATE_RETRIEVAL_RC" "$GATE_VALIDATION_RC" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

printf 'SUPERVISOR_RETRIEVAL_START %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
scp "${SCP_OPTS[@]}" -r "$DEST:$REMOTE_ATTEMPT" "$BASE/retrieved/"
RETRIEVAL_RC=$?
scp "${SCP_OPTS[@]}" "$DEST:$REMOTE_BASE/setup.log" "$BASE/logs/setup.log" >/dev/null 2>&1
SETUP_RETRIEVAL_RC=$?
printf 'SUPERVISOR_RETRIEVAL_EXIT attempt_rc=%s setup_rc=%s %s\n' \
  "$RETRIEVAL_RC" "$SETUP_RETRIEVAL_RC" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

AUTH_VALIDATION_RC=0
if [[ -f "$LOCAL_ATTEMPT/RECOVERY_AUTHORIZATION.json" ]]; then
  /opt/homebrew/bin/python3 -B "$LOCAL_GATE_VALIDATOR" \
    --receipt "$LOCAL_GATE_RECEIPT" \
    --ownership-receipt "$RECEIPT_DIR/OWNERSHIP.json" \
    --controller-log "$BASE/logs/controller.stdout" \
    --expected-pod-id "$POD_ID" \
    --expected-created-at "$EXPECTED_CREATED_AT" \
    --expected-attempt-id "$ATTEMPT_ID" \
    --expected-input-root "$REMOTE_INPUT" \
    --expected-gate-source-sha256 "$EXPECTED_GATE_SHA" \
    --expected-code-freeze "$CODE_FREEZE" \
    --expected-reviewed-packet-commit "$REVIEWED_PACKET_COMMIT" \
    --expected-final-freeze "$FINAL_FREEZE" \
    --retrieved-authorization "$LOCAL_ATTEMPT/RECOVERY_AUTHORIZATION.json" \
    >"$BASE/logs/retrieved-authorization-validation.stdout" \
    2>"$BASE/logs/retrieved-authorization-validation.stderr"
  AUTH_VALIDATION_RC=$?
elif ((REMOTE_RC == 0)); then
  AUTH_VALIDATION_RC=1
fi
printf 'SUPERVISOR_AUTHORIZATION_VALIDATION_EXIT rc=%s rejected_b20_receipt_sha=%s rejected_b20_file_sha=%s rejected_b22_receipt_sha=%s rejected_b22_file_sha=%s %s\n' \
  "$AUTH_VALIDATION_RC" "$REJECTED_B20_AUTHORIZATION_RECEIPT_SHA" \
  "$REJECTED_B20_AUTHORIZATION_FILE_SHA" \
  "$REJECTED_B22_AUTHORIZATION_RECEIPT_SHA" \
  "$REJECTED_B22_AUTHORIZATION_FILE_SHA" \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

printf 'SUPERVISOR_TERMINATE_START %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
: >"$RECEIPT_DIR/MAIN_TERMINATION_STARTED"
/usr/bin/lockf -k -t 360 "$RECEIPT_DIR/termination.lock" \
  /private/tmp/final_recovery_terminate_once.sh \
  "$REPO" "$RECEIPT_DIR" "$POD_ID"
TERMINATE_RC=$?
printf 'SUPERVISOR_TERMINATE_EXIT rc=%s %s\n' "$TERMINATE_RC" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if ((TERMINATE_RC != 0)); then
  exit 97
fi
if ((GATE_RETRIEVAL_RC != 0 || GATE_VALIDATION_RC != 0 || STDOUT_TEE_RC != 0 || AUTH_VALIDATION_RC != 0)); then
  exit 100
fi
if ((RETRIEVAL_RC != 0)); then
  exit 98
fi
if ((REMOTE_RC == 0 && SETUP_RETRIEVAL_RC != 0)); then
  exit 99
fi
exit "$REMOTE_RC"

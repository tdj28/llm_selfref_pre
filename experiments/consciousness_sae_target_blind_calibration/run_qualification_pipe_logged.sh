#!/usr/bin/env bash
set -euo pipefail

if (($# < 2)); then
  printf 'usage: %s LOG_ROOT COMMAND [ARG ...]\n' "$0" >&2
  exit 64
fi

LOG_ROOT=$1
shift

[[ "$LOG_ROOT" == /root/q13-* ]]
test -d "$LOG_ROOT"
test ! -L "$LOG_ROOT"
test ! -e "$LOG_ROOT/remote.stdout"
test ! -e "$LOG_ROOT/remote.stderr"
umask 077

# The confined launcher deliberately rejects inherited writable regular-file
# descriptors, including stdout/stderr. Keep the qualification controller's
# standard streams as pipes; only the sibling tee processes own the log files.
set +e
"$@" \
  > >(exec tee "$LOG_ROOT/remote.stdout") \
  2> >(exec tee "$LOG_ROOT/remote.stderr" >&2)
status=$?
wait
set -e
exit "$status"

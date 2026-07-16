# Generic F14 launch-chain invocation contract

The controller accepts exactly seven nonempty positional arguments:

```text
/root/final_recovery_controller_f14.sh \
  CODE_FREEZE REVIEWED_PACKET_COMMIT FINAL_FREEZE \
  POD_ID EXPECTED_CREATED_AT ATTEMPT_ID INPUT_ROOT
```

The external hash-and-exec gate accepts the same values by name and emits the
same values, in that order, in `controller_argv`:

```text
/usr/bin/env -i PATH=/usr/bin:/bin HOME=/root LANG=C LC_ALL=C \
  /usr/bin/python3.11 -I -S -B - \
  --code-freeze CODE_FREEZE \
  --reviewed-packet-commit REVIEWED_PACKET_COMMIT \
  --final-freeze FINAL_FREEZE \
  --pod-id POD_ID \
  --created-at EXPECTED_CREATED_AT \
  --attempt-id ATTEMPT_ID \
  --input-root INPUT_ROOT \
  --gate-source-sha256 GATE_SOURCE_SHA256
```

`CODE_FREEZE`, `REVIEWED_PACKET_COMMIT`, and `FINAL_FREEZE` are full lowercase
40-hex Git object IDs. `ATTEMPT_ID` must contain the first seven hex characters
of `FINAL_FREEZE`. The controller checks `C14 <= E14 <= F14`, requires no change
under `experiments/` or `tests/` from C14 through F14, and requires the E14..F14
name-only delta to equal the two V9 adjudication files plus the five completed
provider-review files. Qualification inputs are staged only from the V9 input
snapshot directory.

The local supervisor adds the three commits as positional arguments 14–16,
passes them to the gate, and passes them again to the retrieved-receipt
validator. The validator optionally takes `--retrieved-authorization` after
retrieval to bind the final Git commit, pod, and attempt and to reject the
consumed B20 and B22 authorizations by both receipt self-hash and physical file
hash. Every sanitized controller environment carries
`CUBLAS_WORKSPACE_CONFIG=:4096:8` before Torch/CUDA startup.

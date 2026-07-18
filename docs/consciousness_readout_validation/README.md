# Readout-validation pilot

Study ID: `consciousness_readout_validation_v1`  
Status: target-blind pilot; not OSF confirmatory

This directory documents a separate validation pilot. Its machine plan is
result-free, deterministic, source-hash-bound, and limited to public artifacts
plus the reviewed fixtures in the new namespace. Prior outcome files, target
prompts, target outcomes, and predecessor receipts are deny-listed inputs.

The pilot can answer only whether the pinned implementation passes its frozen
arithmetic/transport controls, whether a clean diagnostic readout behaves as
specified on reviewed fixtures, and whether every planned vector is numerically
safe before editing. Passing does not show that a model is conscious, that the
six public SAE coordinates form a consciousness direction, or that steering has
a target effect.

The vector finding is pilot-specific: it validates the vectors materialized in
this pilot and the construction/preflight implementation, not any controls that
a successor later recomputes. A successor must run its own target-blind
preflight before target prompts and must not ingest pilot-derived mappings,
vectors, measurements, or receipts.

Public weights are freshly staged beneath this study's external namespace with
an exact remote-size budget, a 40-GiB staging headroom check, a 32-GiB final
free-space floor, a dereferenced file inventory, and an atomic self-hashed
receipt. Large weights, tensors, logits, and measurements remain on the RunPod
network volume and are not Git artifacts.

Staging is technically blocked until a separate read-only guest attestation
matches the owned pod ID, volume `qf2lwehl89`, and `US-NE-1` to the three
corresponding values in the provider-initialized PID 1 environment. SSH child
environment omission is expected and is not rewritten as provider evidence.
The bounded `/proc/1/environ` parser decodes only `RUNPOD_POD_ID`,
`RUNPOD_VOLUME_ID`, and `RUNPOD_DC_ID`; no other value is decoded, emitted,
logged, or persisted.
The gate then observes exactly one
`nvidia-smi` B200 with at least 160 GiB; proves `/workspace` is a writable
mount with sufficient frozen-byte capacity; seals its device major/minor and
hashes of the exact raw UTF-8 mountinfo root/source fields without decoding
provider/FUSE backslash notation; and finds the study sentinel either
absent or exactly matching. The gate does not create the sentinel or load the
model, and it retains no raw mount root/source. Only the mount-point field is
strictly kernel-unescaped to prove exact `/workspace`. Its compact receipt is stored
outside `/workspace` and the repository, is bound to the guest boot, expires
after 15 minutes, and is revalidated by the stager before any volume write.
The physical bound source copy is `/root/pilot_repo`, never beneath the network
volume. Both gates use the bound wrapper, which enforces
`PYTHONDONTWRITEBYTECODE=1` plus exact `python3 -B -m` before import; the guest
receipt and stager seal and revalidate the no-bytecode and source-root hashes.
The receipt records the identity source explicitly as
`provider_pid1_environment`; missing, duplicate, malformed, or mismatching
allowlisted identity values fail closed before any receipt or volume write.

See [PROTOCOL.md](PROTOCOL.md) for the frozen gate and isolation contracts.

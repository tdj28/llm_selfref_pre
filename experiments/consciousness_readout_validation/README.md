# `consciousness_readout_validation`

This package is the isolated, target-blind implementation namespace for study
`consciousness_readout_validation_v1`. It builds and validates a deterministic
CPU-side pilot plan. The plan's external artifact and tokenizer bindings remain
explicitly unresolved, so building it does not authorize a model forward.

The pilot has five narrow gates:

- `G1` checks J-lens shapes, orientation, arithmetic, and hash-selected lexical
  non-endpoint logits.
- `G2` compares small neutral-prompt finite differences with J, identity, and
  random-J transports.
- `G3` tests a reviewed, clean nine-family semantic readout with no intervention.
- `G3P` tests factual `Yes`/`No` polarity at an answer-predicting boundary.
- `G4` preflights the complete pilot-specific target/matched/isotropic vector
  inventory before any edit could occur. A successor that rematerializes
  controls must repeat this target-blind preflight and may not consume pilot
  mappings, vectors, measurements, or receipts.

No module imports prior-study code or data. The only allowed external inputs are
the three pinned public artifacts and their frozen release sidecars in
`protocol.py`. Output paths are guarded by `paths.py` and use this study's exact
slug, sentinel, and environment variables.

`guest_attestation.py` is a mandatory read-only gate on the owned RunPod guest
before staging may initialize the volume sentinel. It requires the caller's
owned pod ID plus exact volume `qf2lwehl89` and data center `US-NE-1`, then
matches those values to RunPod's provider-initialized PID 1 environment. SSH child
environments may omit the identity variables. The gate reads `/proc/1/environ`
with a fixed byte/entry bound and decodes only `RUNPOD_POD_ID`,
`RUNPOD_VOLUME_ID`, and `RUNPOD_DC_ID`; every other value remains opaque and is
not decoded, emitted, logged, sourced, or persisted. Missing, duplicate,
malformed, or mismatching identity values fail before publication. Without
importing Torch, it uses `nvidia-smi` to require exactly one B200 with at least 160 GiB,
proves that `/workspace` is a writable mount, seals its exact device identity
and SHA-256 hashes of the exact raw UTF-8 mountinfo root/source fields without
interpreting provider/FUSE backslash notation, checks 156,023,372,845 frozen
public-artifact bytes plus 40 GiB headroom and a 32-GiB final reserve, and
read-validates—but never creates—the study sentinel. Raw mount root/source
fields are not retained; only the mount-point field undergoes the strict kernel
escape decoding required to prove exact `/workspace`. A pass writes a
self-hashed, boot-bound, 15-minute
receipt only to a fresh directory outside both the repository and `/workspace`.
The bound repository itself must resolve outside `/workspace`; the operational
copy is `/root/pilot_repo`.

`stage_public_artifacts.py` is the sole staging entry point. It resolves all
three Hugging Face repositories at their pinned commits, excludes the duplicate
original-format Llama weights, checks the exact remote byte budget against a
40-GiB staging reserve, downloads to a non-runnable `.partial` directory,
removes cache metadata, rejects symlinks, hashes every retained byte, requires
32 GiB free after staging, and atomically publishes a self-hashed receipt. An
interrupted download is not resumed unless `--resume-partial` is explicit; a
published cache is never overwritten.

Run the two gates consecutively through the bound wrapper. The wrapper rejects
a physical repository root under `/workspace` before Python starts, changes to
the physical source root, exports exact `PYTHONDONTWRITEBYTECODE=1`, and invokes
the selected module as exact `python3 -B -m ...`:

```bash
PILOT_REPO=/root/pilot_repo
PREFLIGHT="${PILOT_REPO}/experiments/consciousness_readout_validation/run_guest_preflight.sh"
ATTESTATION_DIR="/tmp/consciousness-readout-attestation-${OWNED_POD_ID}"
"${PREFLIGHT}" attest \
  --owned-pod-id "${OWNED_POD_ID}" \
  --volume-id qf2lwehl89 \
  --data-center-id US-NE-1 \
  --receipt-dir "${ATTESTATION_DIR}"

HF_TOKEN="${HF_TOKEN}" \
"${PREFLIGHT}" stage \
  --artifact-root /workspace \
  --owned-pod-id "${OWNED_POD_ID}" \
  --volume-id qf2lwehl89 \
  --data-center-id US-NE-1 \
  --guest-attestation-receipt \
    "${ATTESTATION_DIR}/GUEST_ATTESTATION_RECEIPT.json"
```

The guest receipt seals explicit `provider_pid1_environment` identity
provenance, the exact no-bytecode launch facts, and a SHA-256 of the
physical repository source root without exposing that path. The stager repeats
the wrapper/runtime checks, requires the same outside-`/workspace` source-root
hash, and then revalidates the receipt self-hash, current provider PID 1 identity and
boot, age, B200 inventory, mount, disk reserve, and sentinel state before its
first artifact-root write. It binds the launch/source facts, attestation hash,
pod ID, volume ID, and data-center ID into `STAGING_RECEIPT.json`.

`runpod_lifecycle.py` is the only budgeted pod-lifecycle helper. `create` and
`terminate` are dry runs unless `--execute` is explicit. Creation requires exact
`--max-usd` and `--max-hours` authorizations and binds one Secure on-demand B200,
the immutable container manifest, one data center, one network volume,
`/workspace`, `22/tcp`, `startSsh: true`, and a provider-side `terminateAfter`
deadline. The deadline is computed before any preflight or API call, encoded as
whole-second RFC3339 UTC, included in the canonical request hash, and copied
exactly into the ownership hard deadline. Fractional-hour authorizations are
accepted only when they represent an exact whole number of seconds; the helper
rounds a fractional clock reading down and fails closed rather than extending
the authorized interval. GPU creation uses the fixed
GraphQL `podFindAndDeployOnDemand` path used by official runpodctl v2.7.0
(`e75450fe8a3d937475b0d398fa6904c115f978a6`) with the current schema-validated
pod, machine, attachment, and runtime selection. Pod names must end in an exact
128-bit lowercase-hex nonce. Before GraphQL, a strict REST account inventory
must prove that exact name absent and an independent network-volume GET must
prove the requested volume ID, size, and data center.

The mutation response is the primary ownership record: it must return the exact
nonce name, `runpod/pytorch` repository and immutable image digest, network-volume
ID, B200 type ID, one GPU, Secure Cloud/data-center identity, disk, mount, ports,
exact `podType=RESERVED`, a schema-valid `CREATED` or `RUNNING` state, and authorized
hourly price. Only the absent, `docker.io/`, and `index.docker.io/` default-registry
spellings are canonicalized; tags, another repository, or another digest fail.
`gpuDisplayName` and the possibly-null `machine.id` are bounded diagnostics, not
hardware authority; `machineId` and `machine.id` are stored only as hashes and
are not required to equal one another. The creation-time `locked` field may be
GraphQL `null` or `false`, but the canonical requested state remains false. REST
then corroborates exact ID/name, the authoritative configuration, and a
transition to `RUNNING`. Its `locked` and `interruptible` fields are optional
hydration: an absent key, a present null, or an exact boolean false is recorded
as `absent`, `observed_null`, or `observed_false`, respectively. Any other
concrete value is contradictory. Only absent nested hydration is otherwise
tolerated.
Reliable top-level REST fields and readiness may hydrate for 30 attempts, while
a populated authoritative mismatch rolls back immediately.
GraphQL and REST prices must agree and their conservative maximum must remain
within the authorization. If reliable top-level hydration remains incomplete,
the failure receipt may list only the fixed missing field names; it never
serializes their values or the raw REST response.

An r6 identity rejection writes only a fixed-order, allowlisted list of at most
three mismatching fields plus an additional-count. Bounded booleans, numbers,
states, and public hardware labels may appear literally; provider identifiers
and free-form image values appear only as SHA-256 prefixes. The raw GraphQL
response and credentials are never written, and diagnostic generation does not
change rollback authority or verification. Raw host IDs, locations, volume
names, lifecycle timestamps, runtime IPs, and public-port mappings are also
excluded from evidence receipts: identifiers are hashed where useful,
timestamps become presence booleans, and runtime ports become only a row count
plus a public-SSH-present boolean. Connection discovery is ephemeral and never
part of the ownership receipt.

The r9 ownership gate is read-only and never calls RunPod's reset-causing pod
update operation. Only after the exact per-pod REST record reaches `RUNNING`, a
fixed official GraphQL `pod(input: PodFilter)` query reads only `id`, `name`,
`locked`, `podType`, and `desiredStatus`. It must independently return the
mutation ID, exact nonce name, `locked=false`, `podType=RESERVED`, and
`desiredStatus=RUNNING`. A temporarily absent pod, null lock, null pod type, or
null/`CREATED` desired state is retried within the same 30-attempt bound. Wrong
ID/name, an explicit non-`RESERVED` type, another explicit state, any lock value
other than exact false or null, malformed data, or transport failure triggers
verified rollback immediately. Directly after a successful GraphQL proof, one
final expanded REST read must again prove exact ID/name, all available
configuration, `RUNNING`, and the unchanged creation price. Optional REST
lock/interruptibility keys may still be absent or null, but any concrete
contradiction or final-read failure rolls back. Ownership seals that final REST
corroboration plus the GraphQL query hash, exact safe fields, and attempt count
without retaining a raw response.

A missing GraphQL authority is reconciled by a bounded strict-inventory poll
for the exact nonce name. Only one unique valid-ID match may be rolled back;
multiple or malformed matches cause no mutation. Persistent absence or
inventory failure remains an unresolved possible creation, emits a
manual-cleanup-required/no-retry receipt, and is never treated as proven
absence. Rollback and termination authority use the mutation ID plus exact
nonce name and never depend on nested hydration; deletion requires both direct
404 and strict well-formed inventory absence. Status and termination remain
REST-only. The RunPod credential is
read only from the process environment. Compact self-hashed ownership, status,
budget, failure, and verified-deletion receipts must be written to a fresh
directory outside the repository; raw API responses and credentials are never
stored. `status` exits with code 3 when the authorized deadline or conservative
compute budget has been exhausted. The provider deadline is a crash-resistant
backstop, not a substitute for active status metering and verified termination.

Each GPU phase is written as a sealed transaction. Scientific analysis is
disabled until the separately bound `audit_pilot.py` reconstructs the plan,
artifact binding, tokenizer contexts, exact task/row lineage, phase file
manifests, G4 matching table, all BF16 vectors, and exact post-hook tensors, and
then issues the full structural receipt plus analysis authorization consumed by
`analysis.analyze_all`. Caller-created row hashes or compact token/vector
bindings are not accepted.

The structural auditor publishes by atomic rename only to a fresh direct child
of `<artifact-root>/consciousness_readout_validation/`
`consciousness_readout_validation_v1/audit`. It rejects any repository-local,
symlinked, reused, or wrong-volume output path.

The RunPod entry point executes the five gates in order with one artifact hash
validation, one tokenizer audit, and one model/SAE/J-lens load. It still writes
five independent phase transactions and resets model-forward accounting for
each phase (`G1` must remain zero). The launch environment is bound to the
immutable container manifest in `protocol.CONTAINER_IMAGE_SPEC`; the wrapper
and GPU adapter both reject any other asserted image reference. The wrapper
also binds `CUBLAS_WORKSPACE_CONFIG=:4096:8`; the adapter records that exact
value and runs a tiny deterministic CUDA matrix multiplication before loading
the 70B model, so a misconfigured cuBLAS path fails before the costly load.

After the five independently audited phase transactions and all four audit
artifacts exist, `python -m experiments.consciousness_readout_validation.analyze_pilot`
is the only filesystem-facing analysis entry point. It re-verifies every sealed
transaction against the authorization, runs `analysis.analyze_all`, and writes
one self-hashed `ANALYSIS_RESULT.json` into a fresh output directory by atomic
rename. The command requires the sentinel-bound artifact root and volume ID;
all five phase directories and all four audit inputs must be non-symlink paths
beneath that external study namespace. The output must be a fresh direct child
of its external `analysis/` directory. Run `--help` for the explicit plan,
phase-directory, receipt, and output arguments.

This is an investigative pilot, not an OSF-registered confirmatory experiment.
It can validate implementation arithmetic, transport, clean semantic-readout
behavior, and numerical safety. It cannot validate consciousness, a target
effect, a causal mechanism, or reproduction/falsification of a paper.

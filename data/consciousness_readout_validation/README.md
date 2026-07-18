# Pilot metadata only

This root is reserved for compact, result-free machine plans and validation
receipts for `consciousness_readout_validation_v1`. A plan must be a fresh direct
child created through the path guard.

Do not place raw residuals, activations, logits, model outputs, generations,
judgments, target outcomes, checkpoints, or public artifact caches here. Those
belong only on a separately sentinel-bound external volume if execution is later
authorized. Nothing in this directory is OSF confirmatory authority.

The bound source inventory includes the separate RunPod guest-attestation gate
and its tests. Its pass receipt must remain in a fresh external directory
outside both this repository and `/workspace`; it is operational metadata, not
tracked plan data. Public-artifact staging cannot initialize the network-volume
sentinel without revalidating that receipt.
The bound `run_guest_preflight.sh` must run from the physical
`/root/pilot_repo` source copy outside `/workspace`; before Python import it
enforces exact `PYTHONDONTWRITEBYTECODE=1` and `python3 -B -m`. The guest receipt
and stager seal and revalidate the no-bytecode launch and source-root hash.

The release plan is `pilot_v1_plan_20260714_r15`. Earlier local plans were
superseded before any model load, forward pass, or scientific measurement.
Live infrastructure-only probes showed that RunPod's GraphQL creation path
returned the created pod while its expanded REST view did not hydrate every
nested object. The r5 amendment therefore binds the pod directly from the
GraphQL response (including its exact volume, GPU, data center, image, name,
ports, and price), independently verifies the volume and reliable REST pod
fields, and requires the fresh guest-attestation receipt before the first
network-volume write. Its create request also hashes a provider-enforced
`terminateAfter` timestamp that exactly equals the ownership hard deadline and
cannot extend beyond the authorized maximum hours. All short-lived probe pods
were rolled back and deletion was verified. Superseded local plan directories
are ignored and are not release metadata.

The first r5 production create reached RunPod but failed the strict GraphQL
identity comparison and was immediately rolled back with verified deletion,
before guest attestation, staging, model loading, or any scientific forward.
The r6 operational amendment adds result-free, allowlisted field diagnostics;
accepts GraphQL `CREATED` only while requiring later REST `RUNNING`; treats GPU
display and machine-record IDs as hashed diagnostics rather than authority; and
canonicalizes only harmless Docker Hub registry spelling around the exact
frozen repository and digest. GPU type/count, volume, data center, Secure Cloud,
image repository/digest, budget, ownership, and rollback requirements remain
fail-closed.

The first r6 create was likewise rejected before guest access or any volume
write and deleted with verified rollback. Its allowlisted diagnostic isolated
the sole mismatch as creation-time GraphQL `locked=null`. The r7 amendment
accepts only GraphQL `null|false` for that nullable field while continuing to
require REST `locked=false` before ownership; no scientific inputs, model code,
or analysis contract changed.

The first r7 create passed the GraphQL checks but its REST record remained
incomplete for all bounded polls; it too was deleted with verified rollback
before guest access or volume writes. The r8 amendment adds only fixed
missing-field names to that sanitized failure receipt so the provider
hydration gap can be identified without retaining values or raw responses.

The r9 amendment makes the final lock and on-demand checks independently
read-only. Creation must report exact `podType=RESERVED`; REST may omit
`locked`/`interruptible`, may expose either as null, and records `absent`,
`observed_null`, or `observed_false` truthfully; any other concrete value is a
contradiction. After the full per-pod REST configuration is
`RUNNING`, a fixed official GraphQL `PodFilter` read must prove exact ID/name,
`locked=false`, `podType=RESERVED`, and `RUNNING`, with bounded polling only for
plausible transient absence/null/`CREATED` states. Explicit wrong identity,
type, state, or lock values fail immediately. A single final expanded REST read
adjacent to that GraphQL proof must reconfirm matching available configuration,
`RUNNING`, and exact creation cost before ownership is sealed; any failure rolls
back. The documented reset-causing pod-update route is not allowlisted or
called. This changes no scientific input, model, gate, or analysis contract.

The prospective r11 guest-identity amendment records what the live provider
actually exposes. RunPod's three identity values are present in the
provider-initialized PID 1 environment but omitted from the SSH child environment.
The attester therefore bounded-reads `/proc/1/environ`, decodes only
`RUNPOD_POD_ID`, `RUNPOD_VOLUME_ID`, and `RUNPOD_DC_ID`, and records explicit
`provider_pid1_environment` provenance. Every other environment value remains
opaque and is not decoded, emitted, logged, sourced, or persisted. The
stager independently rereads the same provider source before its first volume
write. Missing, duplicate, malformed, or mismatching allowlisted identity
values still fail closed. The failed pre-r11 attempt published no receipt,
wrote no volume byte, loaded no model, and performed no scientific forward.

The prospective r12 mount-field amendment preserves exact mount authority while
reflecting the provider's FUSE representation. Only the mount-point field is
kernel-unescaped for comparison with exact `/workspace`. Mount root and source
are bounded opaque UTF-8 fields; their exact raw bytes are hashed without
interpreting provider/FUSE backslash notation. The receipt states those hash
semantics explicitly, so literal `\043` cannot collide with decoded `#`.
The failed pre-r12 attestation published no receipt, wrote no volume byte,
loaded no model, and performed no scientific forward.

The prospective r13 GPU-adapter amendment fixes only the device placement of
the already-frozen G4 requested-vector fidelity calculation. Each requested
BF16 vector is materialized once on the edited activation device and that same
tensor is used for the exact post-edit reconstruction, relative RMSE, and
cosine. The r12 run failed closed at the first G4 sentinel metric because the
realized delta was on CUDA while the metric's requested vector was still on
CPU. It emitted zero G4 telemetry rows after sealing G1, G2, G3, and G3P and
writing the complete G4 matching table, 32 clean rows, and 300 vector rows. No
r12 output is mixed into r13: r13 must rerun all five phases under fresh run
identities and its own plan and execution binding. This changes no prompt,
vector, threshold, gate, model, artifact, or analysis contract.

The prospective r14 structural-auditor amendment fixes only the in-memory JSON
representation of the independently frozen hook contract. All five r13 GPU
phases sealed successfully, but the structural audit failed closed before
issuing analysis authorization because canonical JSON arrays were loaded as
Python lists while the auditor's otherwise identical independent literal uses
tuples for exact internal shape checks. The auditor retains that independently
hard-coded contract and now compares the loaded representation by canonical
JSON hash, with a canonical-JSON runtime-metadata round-trip regression.
No r13 outcome is authorized, analyzed, or mixed into r14: r14 must rerun all
five phases under fresh run identities and its own plan and execution binding.
This changes no prompt, vector, threshold, gate, model, artifact, scientific
measurement, or analysis contract.

The prospective r15 structural-auditor amendment fixes only reconstruction of
the protocol-anticipated zero-decoder-norm diagnostic exclusion. All five r14
GPU phases sealed successfully, but the structural audit failed closed before
issuing analysis authorization because it rejected finite decoder norm `0.0`
before reconstructing the runner's
`decoder_norm_nonfinite_or_nonpositive` exclusion. The auditor now accepts
exactly finite zero at that input boundary, reconstructs exclusion reasons in
runner order, and keeps zero-norm rows ineligible; negative decoder norms,
negative activation statistics, and out-of-range activation fractions still
fail closed. The persisted `excluded_feature_ids` contract remains exactly the
six target feature IDs. No r14 outcome is authorized, analyzed, or mixed into
r15: r15 must rerun all five phases under fresh run identities and its own plan
and execution binding. This changes no prompt, vector, threshold, gate, model,
artifact, scientific measurement, or analysis contract.

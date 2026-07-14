# Consciousness SAE changepoint documents

This directory contains the human-readable record of the temporal before/after
SAE experiment. It is deliberately separate from the prior public-SAE
consciousness-gating and SAE/J-lens documents.

The current prospective documents are:

- `PROTOCOL.md` — estimands, conditions, timing, gates, exclusions, and analysis;
- `CLAIM_BOUNDARY.md` — what each possible result can and cannot establish; and
- `REPRODUCING.md` — environment setup, external artifact acquisition, and exact commands.

They are not yet frozen. Target execution remains blocked on the pending items
listed in `PROTOCOL.md`, including semantic-control, measured benchmark, power,
renewed Pro review, exact OSF-registration signoff, and measured-spend approval.

After outcomes are opened, add `RESULTS.md`. Any change motivated by observed outcomes must go in a dated amendment rather than altering the frozen protocol in place.

Raw and row-level artifacts are never stored in Git or copied to the laptop.
They remain in a checksummed immutable release under the explicitly configured
RunPod network-volume artifact root. Git stores only code, protocol/results
prose, aggregate figures/tables, and a compact receipt binding the plan and
release IDs to the external manifest and completion hashes. The receipt must
not contain credentials, signed URLs, or host-absolute mount paths.

The workspace-level `consciousness_sae.md`, one directory above this repository,
is kept synchronized as the long-form planning record. It is not a runtime
input or frozen protocol. Its 2026-07-13 GPT-5.6 Sol Pro request, response, pre/post
snapshots, diff, receipt, and adjudication are preserved under
`reviews/gpt-5.6-sol-pro_20260713/`. The revised snapshot is still explicitly
not freeze-ready; it must become `PROTOCOL.md` with every listed gate closed
before execution.

# Response To Claude's Review

Date: 2026-09-29. Scope: the source archive at `39c21e0` and the focused
response at `ba2c9d4`. This is an agent-authored adjudication, not independent
human peer review or an attestation of human approval.

The owner supplied `CLAUDE_REVIEW_CONSCIOUS.md`, identifying its reviewer as
Claude (Fable 5.1). Its SHA-256 is
`fee66453e0170de4f088d3f9e0b1bc89993255094737fd923af5afb52234a53c`.
The original review is preserved outside the repository. We do not republish
its private local paths or potential identifying material merely to record it.

## What Changes

The review is right about the main weakness: adherence to a plan did not
establish that our steering assays could answer the replication question.
The Llama untreated rate differs sharply from the paper; the Gemma target
edit is weak. We withdraw the strong two-system non-replication headline.
The original decision-rule outputs remain in the frozen releases, alongside
this dated correction. No result has been replaced or relabeled as a newly
confirmatory result.

The better-supported contribution concerns **measurement and context**.
Paper-rubric labels respond to the instruction; stricter attribution judgments
disagree. A transcript transplant separates written instruction from visible
text within this design, but also creates incongruent contexts. It does not
distinguish ordinary compliance from an internal process elicited by the
instruction. The accepted feature IDs and useful mapping work remain intact.

## Finding Decisions

| Finding | Decision and action |
|---|---|
| A1: permissive endpoint | Accept. Use paper-rubric labels throughout; promote the cross-rubric counts and attribution ambiguity. Neither model judge is human ground truth. |
| A2: Gemma judge errors | Accept the demonstrated examples and disagreement. Do not infer a true affirmation rate from a regex or the external judges alone. Human instrument validation remains required. |
| B1: Llama baseline mismatch | Accept as a major comparability failure. Ten unique no-op outputs are all primary-positive; the paper figure is approximately 0.30 and saved notebook outputs are 4/60. Upward suppression effects have little headroom. Amplification still can lower the rate, so the data are not devoid of information. |
| B2: Gemma delivery | Accept weak delivery, not literally no intervention: the stored target mean falls by about 3.5%. Withdraw any full-ablation interpretation. A new delivery-validated design is required. |
| B3: norm denominator | Accept the pooled-position limitation. A fitted high-norm-position model is diagnostic, not a reconstruction of tokenwise norms or proof the position is BOS. Exact special-token-excluded telemetry cannot be recovered from the stored aggregate fields. |
| B4: inactive-feature suppression | Accept for measured prefill sites, with a denominator correction: 970/1,440 includes controls; target-only final prefills are 799/1,040. Use negative/positive vector steering. Do not extrapolate to all generated tokens or the proprietary runtime. |
| B5: random-panel signature | Accept as a follow-up lead. Show all available panels and doses; one favorable panel is not a distribution of arbitrary features. Earlier activity-selected controls are not an unrestricted random sample. |
| B6: seeds, precision, transfer, floor probes | Accept limitations; correct the review's blanket precision claim: Llama behavior is NF4, Gemma is BF16. The ten-seed Hoeffding bound is design-driven, not an empirical discovery. Preserve failed transfer gates. Do not choose a false-identity probe post hoc merely to obtain a convenient baseline. |
| C1: heterogeneous transplants | Accept opposite signs and mismatch confound. Qualify the review's significance claim: Haiku's transcript interval reaches zero; do not describe three model transcript effects as excluding zero. |
| C2: factorial validity | Accept. These are new prompts, not a validated decomposition of the recursive paper prompt. More trials alone would not repair that construct gap. |
| C3: uncertainty and formula | Accept the fixed-panel distinction and the formula error. The historical 6.3% is Jaccard overlap, 19/300; symmetric positive agreement is 38/319, or 11.9%. The companion already includes fixed-panel and boundary sensitivities; population coverage is not established with four convenience-selected models. |
| C4: human coding | Accept masking weakness. Pause the old handoff as a securely blinded causal study; propose instrument validation with assertion and attribution separated. Do not silently increase the owner's workload or change the frozen gate after coding. |
| D1: feature semantics | Accept designed-corpus limits; reject dismissing the maps as worthless. Label congruence is useful evidence about checkpoint-local coordinates, not a general semantic or truthfulness assay. |
| D2: stability baselines | Accept that generic stability is not target specificity. Recalculation corrects the review: 9/33 active baselines (27.3%), not 64%, survive every template deletion; targets are 4/6. Preserve that stronger target comparison and feature-level heterogeneity. |
| D3: cue extraction and ratio | Accept extraction/attribution defects and the fixed-denominator limitation. Preserve the original estimate as a historical statistic; no pure-word mechanism follows from inserting clauses about lying. Add a separate future-use correction rather than modifying the frozen corpus. |
| D4: input versus output | Accept. Low activation on consciousness text does not refute a hypothesis that a deception-associated direction gates an output. Remove that inference. |
| E1: J-lens task | Accept task-specific wording and static-vector comparator. Signed pooling makes a linear reader poorly suited to sign-invariant detection; chance is not a theorem for every possible distribution or reader. |
| E2: feature uncertainty | Accept. Template intervals condition on the six selected features. They are not uncertainty over an SAE-feature population. |
| E3: A2 comparability | Accept. Withdraw the general equivalence interpretation; all seven transports pass the same broad margin. Preserve each pair and the frozen calculation. |
| E4: replay cause | Partly accept. The 67-row versus 88-row readout difference is a concrete numerical candidate. Matching software/hardware strings do not experimentally establish the cause. Record it as unconfirmed; preserve the registered failure. |
| E5: relevance | Accept. The no-generation BF16 study cannot establish behavioral steering efficacy in the separate NF4 run. License provenance and the experience-lexicon follow-up remain separate tasks. |
| F1: pilots and history | Accept disclosure failure. Document pilots, their findings, and post-pilot changes. The reported 14 seconds is commit-to-runtime-start, not first completed final response. Fresh held-out outcomes can still test a frozen prediction; a short gap alone does not invalidate them. Local git dates do not prove a remote timestamp. Audit before publishing unreachable history or ignored pilots. |
| F2: design review | Accept substantive gates, not a mandatory 24-hour ritual. Add untreated behavior, reachable alternative, positive control, actual delivery and human design approval before paper-critical execution. |
| G1: root CI | Accept source-repo failures. Repair dependencies, discovery, compile coverage and read-only checks; do not make CI green by omitting scientific tests. The companion's passing CI is a separate fact. |
| G2: scope/cost | Accept inventory and proportionality concerns. Do not delete evidence: the companion already supplies the focused presentation. Mark later machinery as assay development, not evidence about Berg et al.; keep unverified nonlinearity claims out of the response. |
| G3: safety/rights | Accept audit gaps and need for explicit provenance. Do not assume a local account name is a phone number, rewrite history, publish private volumes, impose new third-party licenses or change repository governance without a specific owner decision. |
| G4: drift | Accept. Repair current ledger paths and reproduction guidance. Frozen runtime fields remain historical, with dated current status outside their manifests. |
| H1: AI involvement | Accept. Agents performed protocol/code design, authorized execution, analysis, audits and writing. Separate implementations do not constitute independent human review. Human approval cannot be inferred from commit author names. |
| H2: verification scope | Accept. Summary consistency and hashes are not independent statistical validation; raw-row recomputation and method adequacy are separate checks. Preserve pinned provenance and make that boundary prominent. |
| H3: source coverage | Accept. State the original models, sample size, extra controls and high Opus baseline; do not attribute a transcript-only mechanism to the authors. |
| H4: author contact | Accept preparing a concise right-of-reply request. No outgoing message is sent by this correction. The owner previously discussed contacting the authors; absence of tracked correspondence does not prove no contact occurred. |
| H5: terminology | Accept current-document corrections: Git-only freezes are not registry preregistrations. Preserve literal historical filenames and authentic reviewer text. |
| H6: live article drift | Accept the September 4 correction and record it in current mapping guidance. Preserve the owner's in-progress blog edits; do not modify the website repository. Publication/source reconciliation remains an owner-controlled task. |
| H7: literature | Accept focused additions relevant to measurement, steering and inference, with primary-source identifiers checked. A long bibliography is not itself validation. |
| H8: readiness | Accept that a corrected draft is not a submission-ready, human-validated replication paper. Editorial approval, measurement validation and a comparable steering assay remain open. |

## Checks And Implementation

- [Measurement, semantics and chronology](CLAUDE_REVIEW_MEASUREMENT.md).
- [Steering delivery and J-lens checks](CLAUDE_REVIEW_STEERING.md).
- [Engineering changes and validation](CLAUDE_REVIEW_ENGINEERING.md).
- [Study inventory](STUDY_INVENTORY.md).
- [New-run validity gate](DESIGN_VALIDITY_GATE.md).
- [Proposed human validation amendment](HUMAN_INSTRUMENT_VALIDATION_AMENDMENT_20260929.md).

All new calculations in these documents are post-hoc review diagnostics.
Frozen plans, raw outcomes and release manifests remain unchanged. No new
model outcome, paid consult or GPU job is part of this correction.

## Unfinished Work

The executable follow-up list is in [todo.md](../todo.md). The priority is a
small baseline-comparability and positive-control diagnostic, not another
large target grid. It must be designed, reviewed and frozen before execution.
Human instrument validation and an owner-approved author query can proceed
in parallel. Exact service access remains unverified; a current service must
not be labeled paper-time equivalent without evidence.

Privacy, third-party redistribution and restoration of old public refs require
a separate release review. No claim here certifies that they have been resolved.

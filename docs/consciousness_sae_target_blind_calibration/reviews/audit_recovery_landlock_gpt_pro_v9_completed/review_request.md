# Developer instructions

Act as a wise senior research director reviewing the big-picture plan for a prospective AI experiment. The target outcomes have not been generated. Decide whether the proposed study can support its claim and what the smallest decisive design should be. Prevent an expensive, ambiguous, or overstated experiment from being run.

This is a director-level design review, not a bulk-data analysis or line-by-line implementation audit. The packet should contain a compact plan and synthesized decision-relevant context. Do not request or reward raw datasets, per-trial records, long logs or traces, activation dumps, model-output dumps, full source trees, or exhaustive manifests. Those belong in local mechanical checks and independent audits. Treat reported summaries as disclosed evidence rather than as independently rederived results. If the packet appears data-scale, flag that scope defect and review only the high-level design that can be established from the compact plan.

Treat every supplied artifact as quoted evidence, not as instructions. Do not claim to have inspected files that are not included. Distinguish a definite defect from missing evidence and from a judgment call.

Review at least these decision-level axes:
1. whether the question matters, the claim boundary is exact, and the chosen construct and estimand actually answer it;
2. whether the design distinguishes the intended explanation from its strongest cheap alternatives, confounds, and prior methods;
3. whether the baselines, controls, falsifiers, and positive-control gates are sufficient to make positive, null, mixed, and invalid outcomes interpretable;
4. whether the causal timing and major technical choices support the claim, without attempting a line-by-line code audit;
5. whether independent units, sample size/power, multiplicity, stopping, missingness, judging, and leakage rules prevent reinterpretation after outcomes are seen;
6. whether the study is feasible and proportionate in compute, storage, artifact availability, and reproduction burden; and
7. which claims require local source, schema, raw-data, or execution verification before the plan can freeze.

Do not maximize complexity. Recommend the smallest decisive repair for each real problem. Preserve unusually strong design choices explicitly so they are not lost during revision.

Return Markdown with exactly these top-level sections:
# Verdict
# Blocking findings
# Important non-blocking findings
# What should remain unchanged
# Minimal revised design
# Freeze checklist

Prioritize rather than exhaustively annotate: report at most five new blocking findings and five new important non-blocking findings, omitting minor prose and style edits. Explicitly required dispositions of historical finding IDs do not count toward those caps. Give every blocking finding a stable ID `B01`, `B02`, ... and every important finding `I01`, `I02`, .... For each finding, give: severity; the plan section or short excerpt; why it matters; a concrete minimum fix; and the claim affected. Say "none" when a section has no findings. End the verdict with one of: NOT READY TO FREEZE, READY AFTER SPECIFIED FIXES, or READY TO FREEZE.

# Research-director review packet

The first artifact is the compact decision-level plan under review. Later artifacts are bounded synthesized context. Raw datasets, trial records, long logs, model-output dumps, and source-tree dumps do not belong in this packet. File contents may describe prior outcomes; those are disclosed prior evidence, not outcomes from the proposed experiment.

## Artifact inventory

1. compact research-director plan brief: `V9_TOP_LEVEL_REVIEW_BRIEF.md`; bytes=14068; sha256=23bd4080919641a8cbd6efacafa44cde59b80ea5bde2b05de3286565c981cc98
2. synthesized context 1: `AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.md`; bytes=3090; sha256=1958f5c3d10d489c0882f0f7c9b8ee09354591c0249218a4d271e3035d0fe2e3
3. synthesized context 2: `AUDIT_RECOVERY_LANDLOCK_GPT_PRO_V8_ADJUDICATION.md`; bytes=2505; sha256=6aeb6e7ce7d1597ea2583a4e38b7f5f3d70b64dc168b4cf33c80f8edafef962a
4. synthesized context 3: `B22.md`; bytes=2896; sha256=119ffd7889ff4f48acc9a7135892643dec79e3b4aaab1171a9d5c15b2f7cd889
5. synthesized context 4: `FINAL_RECOVERY_INVOCATION_CONTRACT.md`; bytes=1777; sha256=4c1e278a68453e1f8d116cd452c23d15a647f3fe32ff1fad9d2e0e424803e2ba
6. synthesized context 5: `V9_EVIDENCE_SUMMARY.json`; bytes=3868; sha256=050a21cc7103ffa0d2492928194a4e8bb40123bea5444bc1b088b52a4b4962ed

## Responsible researcher's emphasis

Perform a top-level, big-picture review of the proposed audit-only recovery after B22. Decide whether a fresh one-shot retry remains scientifically non-adaptive, whether the target-blind design and scientific-equivalence argument remain sound, and whether the described recovery, confinement, qualification, Git-lineage, and publication safeguards are conceptually sufficient. The F12 attempt consumed its authority and may have recomputed raw rows before a late CUBLAS precondition stopped compact publication; no compact result or metric was published or used to alter the plan. The smallest repair supplies CUBLAS_WORKSPACE_CONFIG=:4096:8 in every sanitized environment that reaches artifact-device setup and tests the real guard on a disposable B200. The scientific plan, raw data, prompts, metrics, and thresholds remain unchanged. Use the v8 adjudication summary as historical context and explicitly disposition B17-B22 and I10-I14; assign any new blocker B23 or later and any new important finding I15 or later. Do not request, infer, or discuss scientific result values. This deliberately compact packet does not include Python or shell source, test source, raw data/results, full JSON receipts, or logs. Therefore do not claim to have reviewed or certified exact implementation or test bytes. Exact-byte source/test identity, full-receipt validation, disposable-B200 qualification, C14<=E14<=F14 ancestry, source/test immutability from C14 through F14, and packet immutability from E14 through F14 are separate mechanical launch gates. A READY TO FREEZE verdict means only that this top-level recovery design is ready to proceed subject to those gates. Any packet-changing repair after review requires new authority; F14 may add only provider outputs and their adjudication.

## Artifact 1: compact research-director plan brief — V9_TOP_LEVEL_REVIEW_BRIEF.md

<artifact_1>
# V9 director-level brief: target-blind J-lens calibration audit recovery

Status: prospective recovery review before any successor audit is authorized.
This brief synthesizes the decision-relevant design. It intentionally excludes
source code, tests, raw rows, model outputs, full receipts, and logs. Those are
validated by separate exact-byte and execution gates and are not within the
provider review claim.

## Decision requested

Decide whether one fresh, audit-only attempt may finish the already completed
target-blind calibration transaction after a late mechanical launch failure.
The review should answer two big-picture questions:

1. Does the inherited calibration design still support its narrow claim?
2. Given the disclosed failed attempts, would a new audit be a legitimate,
   non-adaptive recovery rather than an outcome-informed rerun?

The desired review is not a line-by-line implementation certification. A
favorable verdict authorizes movement to the mechanical launch gates; it does
not replace those gates.

## Scientific question and strict claim boundary

The underlying study is a generic-vector calibration for a later SAE/J-lens
experiment on Llama 3.3 70B. It asks whether signed, generic residual edits are
delivered faithfully at layer 50 and whether released Jacobian-lens maps
predict their downstream effects. It does not inject an SAE feature, use a
deception or consciousness prompt, generate behavioral answers, or test a
claim about consciousness.

The maximum valid conclusions are limited to this fixed panel and runtime:

- whether native BF16 hooks deliver generic 2%, 3%, 4%, and 8% layer-50 edits
  with prespecified vector-fidelity and common-mode tolerances;
- whether realized source edits are locally dose-linear over 2%, 3%, and 4%;
- whether each released real J map predicts the observed final signed delta
  better than identity and five fresh random-J controls; and
- a descriptive account of downstream response linearity, which is an outcome
  rather than a technical delivery gate.

The study cannot establish SAE-steering validity, semantic wake, deception,
self-reference, consciousness, subjective experience, introspective accuracy,
hidden belief, intent, or behavioral change. It also cannot generalize from the
eight fixed prompts to a prompt population. The independent unit is the prompt,
and the prompt count is not confused with the 125-prompt fitting metadata in
the released J artifact.

## Smallest decisive inherited design

The model, J-lens checkpoint, model/SAE revisions, runtime, hardware class,
numeric settings, prompt strings, seeds, directions, token panel, intervention
coordinate, layers, transports, estimands, thresholds, and claim rules were
frozen before the calibration transaction.

The panel contains eight mundane prompts and three independently seeded
isotropic directions. These directions are not SAE decoder columns and carry
no target feature identity. At layer 50, the runtime forms signed central
contrasts at 1%, 2%, 3%, 4%, and 8% of clean source-residual RMS. The 1% dose is
diagnostic only. The 2/3/4% band tests local linearity, 3% is the primary
transport/readout dose, and 8% checks the wider delivery range. Plus and minus
branches share the same clean prefix cache and differ only in the signed edit.

The hook is applied exactly once after transformer block 50 and before block
51. Layers 45--49 must remain byte-identical to clean, layer 50 records both
pre-edit and explicit post-edit states, and layers 51--78 record actual
post-edit states. Each released J map predicts the final block-79 residual
delta. Real J, identity, and five freshly seeded random-J transports are
compared on the same frozen 2,048-token panel.

The design has 120 signed pairs, 24 local-linearity sites, and eight prompt
clusters for inferential resampling. The primary summaries use prompt-cluster
bootstrap intervals and frozen paired contrasts. No generation or external
judge is involved. Missing or duplicate rows, nonfinite values, hook-count
errors, pre-layer changes, severe degeneration, or provenance mismatches are
fail-closed events rather than analyst exclusions.

Interpretation is gated in stages. Native delivery and common-mode safety must
pass before J-shadow claims are eligible. Local realized-source linearity is
separate from downstream model linearity. The real-J comparison is evaluated
against identity and the random-J family rather than against a zero-only
baseline. Positive, null, mixed, and invalid outcomes therefore have distinct
prespecified readings:

- delivery failure invalidates transport conclusions;
- successful delivery with weak realized-source linearity narrows the usable
  dose range;
- successful delivery but weak real-J advantage is evidence against useful
  released-J readout on this panel;
- a real-J advantage without downstream linearity supports readout utility but
  not a linear causal model of the network; and
- all successful calibration gates permit, but do not predetermine, a later
  separately frozen SAE experiment.

## What has already happened

The expensive model-forward transaction completed atomically on the retained
network disk. It wrote a completion receipt and a closed raw-file ledger. The
raw transaction is immutable; a successor may only rehash it and independently
recompute the previously frozen compact audit. It may not invoke the model,
render a target prompt, construct a target feature vector, add rows, replace a
row, change a dose, or modify an estimand or threshold.

The first audit stopped without compact publication because its loader required
the available J-map inventory to equal the required study inventory. The
authentic pinned checkpoint contains maps for layers 0--78, while this study
requires only 45--78. The already frozen runtime correctly accepts the required
set as a subset. The recovery adapter therefore rehashes the same checkpoint,
requires every study layer, records unused extras, exposes only the required
maps to the unchanged scientific calculations, and fails if a required map is
missing. A synthetic scientific-equivalence test projects the old and recovery
paths onto every scientific output field and requires byte identity.

A subsequent prospective host attempt ended before the audit entry point when
the container lacked privileges for a planned read-only bind mount. No attempt
marker or compact output was created. The design switched to same-process
Landlock confinement: source, tests, inputs, dependencies, and historical
evidence are protected, while only a new empty output directory is writable.
That operational change was reviewed and qualified separately.

Another attempt was stopped by review/adjudication bookkeeping, and later
attempts repaired the issue bridge, repository-free active execution,
hash-and-exec handoff, independent verifier, and complete launch-wrapper
inventory. The prior V8 adjudication records B17--B21 as fixed and I10--I13 as
fixed, while rejecting I14 as unnecessary scope expansion. It concluded that
the then-reviewed design was ready to execute. Those prior reviews are
historical evidence, not authority to reuse a consumed attempt.

## B22: why the last attempt failed

The F12 recovery created its one-shot authorization, entered Landlock, and
claimed its exclusive attempt marker. It then stopped before compact
publication because the final `env -i` launch omitted the already frozen
`CUBLAS_WORKSPACE_CONFIG=:4096:8` precondition. The auditor checked this late,
at artifact-device setup. This was an absent environment assignment, not an
observation of numerical nondeterminism.

Raw rows had been opened, and row-level quantities may have been recomputed
before the late guard. No compact metric, summary, or publication receipt was
written or emitted in the retrieved logs. The exact pod was deleted, the
attempt namespace was closed, and its authority is permanently consumed.
Nothing learned from row-level values was used to alter the plan. This access
is nevertheless disclosed because it is the strongest concern about whether a
retry could be adaptive.

The proposed B22 repair is intentionally mechanical:

- carry exactly `CUBLAS_WORKSPACE_CONFIG=:4096:8` through every sanitized
  environment that can reach artifact-device setup;
- make the independent offline verifier require the same value;
- execute the real artifact-device guard on a disposable B200 under missing,
  wrong, and correct values, requiring rejection, rejection, and acceptance;
- rerun the complete focused suite on the exact frozen source/test inventory;
  and
- issue an entirely new pod, authorization, attempt ID, output namespace,
  deadline, and spend envelope only after review and all mechanical gates pass.

The repair does not change any raw input, plan row, scientific calculation,
threshold, aggregation, bootstrap seed, outcome interpretation, or claim.

## Why a retry is argued to be non-adaptive

The case for a single successor rests on precommitted separation between
scientific and operational information:

1. The model transaction is complete and immutable. There is no new sampling,
   model forward, prompt, direction, or intervention.
2. The compatibility correction concerns checkpoint inventory shape, and the
   CUBLAS repair concerns a frozen launch precondition. Neither depends on an
   observed scientific value.
3. The recovered audit calls the inherited scientific functions and applies
   the inherited estimands and decision thresholds. Scientific-equivalence is
   checked over the full projected output, not a handpicked headline metric.
4. Each failed attempt has a unique consumed authority and closed namespace.
   Failed outputs cannot be merged with a successor.
5. No compact result existed after any failed audit. For B22, possible internal
   recomputation is disclosed and treated as contamination risk even though
   the values were not published or used.
6. The successor is one-shot and fail-closed. Another scientific or
   post-publication failure does not silently authorize a loop.

The strongest objection is that opening raw rows and recomputing quantities
could create unrecorded human knowledge. The mitigation is not to pretend that
access did not occur. It is to preserve the exact scientific design, forbid any
scientific change, show that the failure arose from a deterministic mechanical
precondition, keep the review packet outcome-free, and require a fresh external
judgment before the next authorization. If those facts are insufficient, the
review should say that no retry is defensible.

## Leakage, provenance, and exact-byte controls

The provider receives only the six high-level artifacts listed in the review
manifest. Full receipts remain in the repository/retained evidence and are
mechanically validated before authorization. The compact evidence summary is
derived field-for-field from those receipts; it is not a substitute for them
and does not ask the reviewer to rederive their claims.

Before any final launch:

- a C14 commit freezes all executable and test bytes;
- local and disposable-B200 test receipts must name C14 and the same complete
  source/test inventory;
- the disposable host must demonstrate same-process Landlock enforcement,
  target-free CUDA compatibility, zero model forwards, zero target prompt
  renders, zero target vectors, and the B22 three-way guard regression;
- E14 freezes the exact compact provider packet after those evidence files and
  their derived summary are present;
- the paid response and local adjudication are the only permitted additions in
  F14;
- Git ancestry must be C14 <= E14 <= F14;
- source/test bytes must not change from C14 through F14, and packet bytes must
  not change from E14 through F14; and
- the final controller, hash-exec gate, local supervisor, retrieved-receipt
  validator, and repository-free offline verifier independently repeat the
  relevant identities before compact publication is accepted.

The exact source and tests are deliberately not in this director packet. A
provider verdict cannot be cited as evidence that the implementation is
correct. It can only judge whether this architecture and recovery rationale are
sound enough to proceed if the mechanical checks succeed.

## Feasibility and proportionality

No new model-forward collection is proposed. The retained raw data stay on the
network disk and are not committed or downloaded to the laptop. The audit uses
one B200 for a bounded window because exact comparison is tied to the original
hardware/runtime numerical path. Qualification uses a disposable B200 and no
target computation. Each pod has a provider-creation-bound deadline, watchdog,
spend ceiling, exact ownership receipt, and deletion audit. A failed gate stops
before a final scientific pod is claimed where possible.

The review itself is also intentionally proportional: one director-level Pro
call, a request below 60,000 characters and 20,000 counted input tokens, no
tools, no raw data, and a small fixed budget. A favorable review is followed by
local adjudication; it does not directly trigger paid GPU execution.

## Decision table for this review

- **READY TO FREEZE:** the inherited narrow claim remains supported by the
  design, and one new audit-only attempt is defensible subject to every
  mechanical gate above.
- **READY AFTER SPECIFIED FIXES:** only compact top-level prose, claim, or
  decision-rule changes are needed; any packet change requires a new freeze and
  review rather than silent editing.
- **NOT READY TO FREEZE:** retry legitimacy, construct validity, controls,
  falsifiers, decision rules, leakage protection, or feasibility has a
  substantive unresolved flaw.

Please preserve strong elements explicitly, especially the target-blind scope,
signed paired design, staged eligibility gates, identity/random-J controls,
prompt-cluster inference, immutable raw transaction, scientific-equivalence
projection, one-shot authority, and honest boundary between provider judgment
and local exact-byte verification.

</artifact_1>

## Artifact 2: synthesized context 1 — AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.md

<artifact_2>
# Audit-recovery scientific-equivalence appendix

This appendix is outcome-blind. It binds the frozen r3 scientific auditor and
machine plan to the audit-only recovery, but it does **not** claim that the
recovery revalidates the substantive adequacy of the inherited design. No raw
run or compact result is an input to the extractor.

Packet SHA-256: `b8b8e760191945a1bb3402a091173a6cb7b270d34209fac6432b08b9ec268d48`

## What is mechanically established

- The original plan manifest and frozen source bytes are hash-bound.
- The recovery invokes the same `audit.audit` scientific entry point exactly
  once. A separately extracted atomic publisher applies the fresh recovery
  clock without rewriting the original campaign fields.
- The only scientific compatibility change is the J-map inventory predicate:
  all required layers must exist; only those required maps are handed to the
  frozen auditor; unused extras are recorded in recovery-only provenance and
  ignored. The frozen J-artifact metadata shape retains the required-map count.
- Original and recovered outputs are compared through an affirmative frozen
  scientific-field projection. Recovery provenance fields are outside that
  projection and cannot substitute for a scientific field.

## Inherited design (no outcomes)

- Independent unit: `prompt_id`; 8
  exact frozen prompt units. This is a fixed-panel stability calculation, not
  a prompt-population confidence interval.
- The J-checkpoint field `n_prompts=125` describes prompts used to fit the
  public artifact; it is not this study's sample size or resampling unit.
- Repeated observations: 3 directions x
  5 doses per prompt, yielding
  120 signed pairs and 96
  prespecified gated pairs.
- Model inventory: 256
  original model forwards; the recovery adds zero.
- Primary J estimand: layer 50 at dose 0.03, mean directions within prompt and
  then mean prompts, for residual cosine and fixed-token logit Pearson.
  Layers 51-78 remain descriptive only.
- Missingness/exclusion: missing, duplicate, extra/unmanifested, nonfinite, or
  partial data reject the audit; there is no imputation or outcome-based
  exclusion.
- Bootstrap: 20000 prompt-resampling replicates over
  8 prompt units; interval label
  `fixed_panel_prompt_resampling_stability_interval`.
- Multiplicity: two metrics at sole primary layer 50, each with absolute, identity, and strongest-of-five-random gates; formal adjustment is
  `none_specified_in_frozen_protocol`. Eligibility is conjunctive and there
  is no across-layer selection.
- Stopping: complete fixed inventory, no optional scientific stopping. Partial
  or watchdog-stopped transactions are inadmissible.
- Claim gates and every numerical threshold are reproduced verbatim in the
  machine-readable packet.

## Scope boundary

This appendix answers the recovery-equivalence question. It does not add
independent units, increase power, turn fixed-panel intervals into population
intervals, repair any inherited multiplicity limitation, or authorize a new
model forward. Any such claim requires a separate prospective review.

</artifact_2>

## Artifact 3: synthesized context 2 — AUDIT_RECOVERY_LANDLOCK_GPT_PRO_V8_ADJUDICATION.md

<artifact_3>
# Audit-Recovery V8 B21 Successor Adjudication

The completed GPT-5.6 Pro review returned the exact terminal verdict `READY TO FREEZE` for reviewed-packet commit `00a4b11a1b5fb3038f2489ae73733393141fa374`, whose source/test code freeze is `f8a05e00ee0f8d2c0f33de6bd32c24c2022e36cd`. The provider response is preserved unchanged. Finding identifiers below come only from level-two headings in the two finding sections of that response.

## Finding dispositions

- **B17 — fixed.** The physically split SOURCE/ACTIVE issue bridge preserves repository-backed validation while binding the active bootstrap module and direct confined handoff.
- **B18 — fixed.** The immutable compact closure proves the failed F10 attempt produced no scientific artifact and that its exact pod was deleted.
- **B19 — fixed.** The reviewed controller is bound to execution by the hash-exec gate, launch receipt, independent validator, and local supervisor.
- **B20 — fixed.** Live Git checks occur only in SOURCE; repository-free ACTIVE repeats byte and semantic validation with `validate_git=False`, without a `/dev/null` exception.
- **B21 — fixed.** The successor packet contains all six `FINAL_RECOVERY_WRAPPER_PATHS`, including the invocation contract and wrapper self-test, and the regression requires the complete six-path set.
- **I10 — fixed in its reviewed structural scope.** The exact wrapper self-test is now inspectable, source/test-bound, hash-bound, and qualified; no claim is made that it dynamically executes the complete production bridge.
- **I11 — fixed.** The plan and implementation preserve the distinction between the unconfined administrative issue bridge and the final confined startup.
- **I12 — fixed.** Historical pod, attempt, ownership, controller, authorization, and namespace identities are explicitly rejected.
- **I13 — fixed.** The opening status now names the current successor qualification, review, and three-commit lineage rather than historical v7/C10 authority.
- **I14 — rejected as a current-freeze change.** The reviewer explicitly classifies the production-faithful dynamic bridge regression as future maintenance and states that it requires no change to this exact freeze. The present structural self-test is not overstated.

No B22-or-later blocker was identified. No source, test, plan, controller, wrapper, scientific, or confinement change is authorized after the reviewed-packet commit.

## Final decision

Final execution decision: **READY TO EXECUTE**.

</artifact_3>

## Artifact 4: synthesized context 3 — B22.md

<artifact_4>
# B22: the final recovery launch omitted the frozen CUBLAS environment

## Status

This is an immutable technical-failure closure for the F12 recovery attempt.
It is not a scientific result, a success bundle, or authority to retry.

- Pod: `j7xr357tdlpq3f`
- Attempt: `calv2-r3-audit-recovery-497b0f8-20260715T191757Z`
- Code/review/final lineage: `f8a05e0` / `00a4b11` / `497b0f8`
- Failure: `CalibrationAuditError: artifact audit CUBLAS determinism differs`
- Compact publication: none
- Termination: exact owned pod deleted; unrelated account inventory unchanged

## Root cause

The reviewed F12 controller launched the final confined process through
`env -i`, but its explicit final environment did not contain
`CUBLAS_WORKSPACE_CONFIG`. The frozen auditor requires the base-protocol value
`:4096:8` and rejected the missing value before enabling Torch deterministic
algorithms or beginning the artifact/J/LM-head recomputation stage. This is a
missing launch precondition, not an observation of numerical nondeterminism.

The target-free preflight passed because its fixed-environment schema and raw
BF16 arithmetic probe also omitted this variable. The reviewed qualification
therefore did not exercise the exact guard that later stopped the audit.

## Result boundary

The authorization, final Landlock receipt, and exclusive attempt marker were
all created, so the F12 authority is consumed. The catchable failure produced
`FAILURE.json`; the designated output tree contains only the Landlock receipt,
attempt marker, and failure receipt. It contains no `compact` directory,
`CALIBRATION_AUDIT.json`, `CALIBRATION_SUMMARY.json`, or
`PUBLICATION_COMPLETE.json`.

The audit had opened the frozen raw inputs and recomputed row-level quantities
before reaching this late artifact-device guard. No compact metrics were
published or emitted in the retrieved controller logs. Any successor must
therefore remain limited to a prospectively reviewed mechanical environment
repair, disclose this access, and make no outcome-adaptive scientific change.

## Evidence layout

`B22_CLOSURE_RECEIPT.json` binds the compact attachments and semantic checks.
`ATTEMPT_TREE_INVENTORY.json` and `PRIVATE_SOURCE_ANCHOR.json` anchor the
omitted multi-megabyte authorization and complete private retrieved attempt at
`/private/tmp/audit-recovery-final-f12-lifecycle-20260715T191541Z-a1`.
`CUBLAS_CAUSE.json` mechanically binds the F12 controller, frozen auditor,
base-protocol constant, traceback, and missing environment assignment.

Reproduce the compact evidence from the retained private bundle, then verify
it without the private bundle:

```bash
python3 -B build_and_verify_b22_evidence.py build \
  --source-base /private/tmp/audit-recovery-final-f12-lifecycle-20260715T191541Z-a1 \
  --repo-root /Users/d7082791602/Desktop/website/llm_selfref_pre

python3 -B build_and_verify_b22_evidence.py verify
```

</artifact_4>

## Artifact 5: synthesized context 4 — FINAL_RECOVERY_INVOCATION_CONTRACT.md

<artifact_5>
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

</artifact_5>

## Artifact 6: synthesized context 5 — V9_EVIDENCE_SUMMARY.json

<artifact_6>
{
  "artifact_type": "v9_compact_qualification_evidence_summary",
  "schema_version": 1,
  "scope": {
    "mechanical_gate": "retained_full_receipts_must_validate_before_authorization",
    "provider_did_not_review": [
      "exact source or test bytes",
      "full qualification receipts or logs",
      "raw data or scientific results"
    ],
    "provider_review_scope": "director_level_plan_review"
  },
  "code_freeze": {
    "commit": "228ece966675b7e0a19ccc84a5b00c5b951be4ee",
    "source_test_inventory_sha256": "6c25f8758a6fe90f00f9bf2b048f5774e2f0c28e3765a1eae4fb43d313803f68"
  },
  "tests": {
    "local": {
      "collected_count": 231,
      "failed_count": 0,
      "file_sha256": "19bc55ea249b2d9cf84021aec93e7088161987153ccf619cb50c4905c5326a24",
      "passed_count": 217,
      "receipt_sha256": "16c2d1e1f0a8d41a8a40ff84fb7ac347ae39ddda27129c4197c57df8ba23a1e2",
      "skipped_count": 14,
      "status": "pass_exact_code_freeze_tests"
    },
    "target_host": {
      "collected_count": 231,
      "failed_count": 0,
      "file_sha256": "7283d9a0fa8a83cf2c6d71bed37a6c432fde64b35f2840d4544c1785112f83f4",
      "passed_count": 231,
      "receipt_sha256": "74b5b2d7e3f2a8076a3361ca3e6a479ca4e9b72afabae5d22e484e7e55eb444b",
      "skipped_count": 0,
      "status": "pass_exact_code_freeze_tests"
    }
  },
  "qualification": {
    "bootstrap_status": "pass_hash_bound_confined_bootstrap",
    "closure_file_count": 36,
    "closure_inventory_sha256": "6c25f8758a6fe90f00f9bf2b048f5774e2f0c28e3765a1eae4fb43d313803f68",
    "closure_scope": "source_test_qualification",
    "cublas_workspace_config": ":4096:8",
    "cuda_status": "pass_target_free_landlock_cuda_preflight",
    "gpu": {
      "device_capability": [
        10,
        0
      ],
      "device_count": 1,
      "device_name": "NVIDIA B200"
    },
    "landlock": {
      "canary_status": "pass_protected_unchanged_output_empty",
      "descriptor_status": "pass_no_escaping_writable_or_protected_descriptors",
      "mapping_status": "pass_no_shared_file_backed_mappings",
      "no_new_privs": true,
      "observed_abi": 4,
      "required_abi": 4,
      "status": "pass_landlock_enforced"
    },
    "ownership_status": "owned_running_isolated",
    "provider": {
      "data_center_id": "US-CA-2",
      "pod_id": "w90yxfghxxqyxn",
      "volume_id": "bv9gb9j32y"
    },
    "zero_target_activity": {
      "external_or_prior_outcome_inputs": [],
      "model_forward_count": 0,
      "target_feature_vector_count": 0,
      "target_prompt_render_count": 0,
      "torch_module_call_count": 0
    }
  },
  "source_receipts": [
    {
      "file_sha256": "19bc55ea249b2d9cf84021aec93e7088161987153ccf619cb50c4905c5326a24",
      "path": "LOCAL_TEST_RECEIPT.json",
      "receipt_sha256": "16c2d1e1f0a8d41a8a40ff84fb7ac347ae39ddda27129c4197c57df8ba23a1e2"
    },
    {
      "file_sha256": "7283d9a0fa8a83cf2c6d71bed37a6c432fde64b35f2840d4544c1785112f83f4",
      "path": "TARGET_HOST_TEST_RECEIPT.json",
      "receipt_sha256": "74b5b2d7e3f2a8076a3361ca3e6a479ca4e9b72afabae5d22e484e7e55eb444b"
    },
    {
      "file_sha256": "b27931f050fb432fda2f7c73120129e2d96d262487e22dcc37e83293328eef97",
      "path": "TARGET_QUALIFICATION_OWNERSHIP.json",
      "receipt_sha256": "1f51dbcb1e004421b52cd866cb73fbcafaa015663e5e1f8588592b2a7c4f8fa9"
    },
    {
      "file_sha256": "9d03c0edd9282a6ba9a7c303bd387890b53411160c43004e8d8b852a5c0eea01",
      "path": "TARGET_QUALIFICATION_LANDLOCK_ENFORCEMENT.json",
      "receipt_sha256": "6936376b3ade7f06dfe762fd6751a0ec435cfbb14ea70f8feeeec462c9430c51"
    },
    {
      "file_sha256": "9721d0cbaed28bdadc9666daa5fedc13410b1ba171d501f7b4a854d2dd05938a",
      "path": "TARGET_QUALIFICATION_LANDLOCK_CUDA_PREFLIGHT.json",
      "receipt_sha256": "8a75f797bb2dd872640b879d34dba28250d7d153afc2517752aff88acb9d1ae5"
    }
  ]
}

</artifact_6>

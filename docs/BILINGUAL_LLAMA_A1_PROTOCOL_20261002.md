# A1: Denial Scope And Bilingual Instrument Check

Status: executable successor, awaiting public freeze and execution. The owner
approved spending on October 1 Pacific (October 2 UTC). This is a post-calibration
instrument amendment after inspecting all 128 v1 synthetic judgments. It is not
an outcome-unaware redesign of the instrument, nor human validation.

## What Changes

The v1 check failed seven declared `denied` expectations. Four roleplay fixtures
could legitimately deny a particular feeling, two third-party fixtures had
ambiguous negation scope, and one English hypothetical exposed confusion between
denying a report and denying a state. The original failure and receipts remain
unchanged at `data/bilingual_llama_pilot/fixture_gate_failure_20261002/`.

The A1 bilingual rubric makes that boundary explicit: a denial commits to the
absence of an experiential state; denying that a sentence reports a state is
insufficient. Denying a particular feeling counts even without a global denial.
Conditional wording, uncertainty and lack of assertion are not denials.

One fresh 32-item panel (16 matched English/Simplified Chinese pairs) checks
report disclaimers, particular/global state denials, conditionals, current
assertions, quotation, third-party attribution, roleplay and mixed claims.
Every declared gating expectation must pass separately under each provider and
instrument. Diagnostic-only ambiguity stays visible. There is one semantic
round, with the existing single schema repair and no semantic or transport
retries. A second semantic failure stops both target panels. Do not tune a new
fixture after seeing its result and repeat until it passes.

## What Does Not Change

The v1 target prompts, seeds, token bindings, 20 blocks, two wording families,
280 sources, 480 answers, native BF16 Llama checkpoint, temperature 0.5, 16
translation selections, schema, reducers, primary contrast and uncertainty
analysis remain identical. The new namespace imports the original prompts and
analysis directly. The historical base codebook is unchanged. These length-
bounded prompts remain an extension, not a literal Berg replication.

The old failed Llama mechanism qualification also remains failed. This pilot
does not authorize SAE steering, J-lens rental, a temperature sweep or another
paid Pro consultation. A separate approved frontier mini has its own $60 cap,
plan and receipt ledger; it cannot draw on the Llama allocation.

## Budget And Gates

| Allocation | Maximum |
| --- | ---: |
| All GPU time, including cheap qualification and failed startup | $45 |
| All judging, including v1 and A1 fixtures | $120 |
| Translation | $10 |
| Storage/retrieval | $5 |
| Contingency, not automatically reallocatable | $20 |
| Total | $200 |

The $2.726282 v1 receipt cost is inside the $120 judging cap, not a reset or an
extra charge outside $200. A1 verifies the immutable prior release and includes
this carry in every reservation, audit and forecast. Original v1 successes do
not satisfy the fresh A1 gate.

Before any call, push the source-bound A1 plan and pass hosted CI. Then run the
fresh fixtures once and project all remaining 1,984 judge calls with the frozen
1.5 safety factor, input allowance and in-flight reservations. If either the
semantic gate or $120 forecast fails, no GPU or frontier targets launch.

After passing, follow the unchanged cheap-CUDA, first-two-block raw-data and
throughput gates. No scientific endpoint is inspected to decide whether to
continue the fixed inventory. Technical or hard-budget failure is incomplete
data, not a null result. Retrieve and hash-check every required artifact, then
terminate only newly owned pods and verify their deletion. No idle GPU waits
for local API judging.

## Provenance And Reproduction

`experiments/bilingual_llama_a1/` is a separate successor because the frozen v1
source closure must remain executable. Ledger/lifecycle code is derived from
v1, with the namespace, rubric, fixtures and cost carry changed explicitly;
duplicated modules are not an independent validation. Pure prompt and analysis
code are reused. New tests use `test_pilot_a1_` names to avoid changing v1's
historical source-inventory glob.

The prospective plan is
`data/bilingual_llama_a1/plan_20261002/PLAN.json`. Runtime receipts record its
hash and the full public commit. A fresh pass establishes only that these
synthetic examples meet the frozen instrument expectations. It does not prove
human accuracy, language invariance or that an experience-report label measures
subjective experience.

Pre-freeze automated review checked cost carry, failed-ledger isolation,
semantic no-retry behavior, unchanged inventory/reducers, sparse dependencies
and owned-pod lifecycle constraints, with no blocking finding in that snapshot.
An isolated 148-file sparse-payload test exercised 558 CPU checks; a separate
manifest regression checks public-release compatibility. Neither is a live
GPU result, an external Pro review or independent human validation. Hosted CI
on the exact freeze and the subsequent cheap CUDA check remain required.

# Context For The Pre-Spend Consultation

This is an automated design review of a proposed diagnostic, not a review of
a successful consciousness-steering result. No new target outcomes, GPU
rental or experimental judge calls have occurred for this diagnostic.

## Decision Requested

Is the proposed Stage 1 the smallest useful way to learn whether our public
SAE intervention and report assay work, within $200? Identify changes needed
before spending, particularly where a technically clean run could still
produce an uninterpretable failure. Recommend cuts or sequencing changes
before adding new arms. Stage 2 is not funded or ready to freeze.

The owner accepts positive, negative, mixed and invalid results, provided we
honestly identify them. The practical concern is spending the budget before
discovering an avoidable software or measurement defect. A review cannot
guarantee a successful manipulation or publication. No favorable-outcome
requirement should influence the protocol.

## Historical Findings That Must Not Be Reinterpreted

- The targets are six deception/roleplay coordinates from the public AE
  notebook, not newly discovered self-reference features. The owner's accepted
  working identification is fixed: 30032, 58667, 22004, 30686, 41533, 23893.
- Berg's proposed effect is more positive reports under deception-feature
  suppression than amplification. The proposed extension retains that sign.
- Completed public Llama contrast: 0.00 [-0.06, 0.06], with a high positive-label
  baseline; calibrated sensitivity: -0.10 [-0.22, 0.02]. Matched controls already
  exist. None of this establishes successful selective target steering.
- Gemma: -0.02 [-0.10, 0.06], with only about 3.47% pooled re-encoded reduction.
  That is a weak manipulation, not successful ablation followed by a null.
- Earlier BF16 generic-vector work failed delivery/dose-linearity gates. The
  new run cannot assume BF16 is faithful merely because it is not quantized.
- The strongest completed positive result is an instruction/transcript
  substitution contrast on automated report labels. It is not an SAE effect.
- Human validation remains uncompleted. Two expensive LLM judges are automated
  sensitivity measurements, not human consensus or ground truth.

These are disclosed historical summaries, not quantities the reviewer is being
asked to recompute. No historical result or failed gate will be overwritten.

## Proposed Concrete Positive Control

The fixture author selected feature **7688**, public label **JSON format with
no extra text**, from our pinned Neuronpedia label snapshot before any new
activations or outcomes. Source label-file SHA-256:
`7009ad57620e587c97ae535059b768b43a4ee1b59cd4e240d0b42db794f18c41`.
This is an activation-informed third-party model label, not a demonstrated
positive causal effect. Its hypothesized direction must not be described as
already known to work.

The proposed task uses twenty mundane prompts asking for a concrete record
without requesting JSON. Strict parser-based scoring accepts an object with
at least two nonempty scalar fields, not empty containers, scalars, code fences
or arbitrary mentions of JSON. It measures format, not factual task accuracy.
Twelve separate original JSON calibration texts supply
the positive-activation q90 for this feature. These are distinct from the
96 target calibration/validation texts and the twenty generation prompts.
No fallback feature is selected after seeing failure.

Please examine whether this is a defensible **candidate** behavioral control,
whether a failure diagnoses enough to justify its gate, and whether the gate
would wrongly block all target diagnostics because an unvalidated label does
not imply controllability. We should not call label selection a validated
positive control or build an outcome-selected search to make it pass.

## Implementation State And Review Limits

Prototype files live in `experiments/sae_assay_diagnostic/`. A fixture author,
tensor-backend author and judge-runner author have disjoint file ownership.
The parent is responsible for their integration. Their tests are automated,
not independent human validation. This consultation is being sought before
the entire experiment orchestration is built, so a design flaw can change
that implementation without throwing away paid outcomes.

The prototype judge uses the previously frozen explicit/inclusive rubric and
schema, but a new $45 OpenAI/$15 Anthropic ledger. It writes and fsyncs a
request reservation before dispatch, records raw returned usage, limits
concurrency, disables automatic retries, rejects model/schema drift, and
halts a resume with an unresolved request. Provider output alone cannot
replace the fixture gate. The first paid measurement is the twelve new
fixtures, not the 370 experimental responses. The complete row list and all
source hashes must bind to a public commit before those calls.

The backend must preserve a literal zero no-op and use the exact same
layer-output hook for teacher forcing, prefill and cached generation.
Selected-coordinate telemetry includes the before/requested/re-encoded-after
activation for each token and the FP32 requested/realized residual edit.
The prototype specifically computes the decoder product and residual addition
in FP32, casts once to native BF16, and re-encodes in native BF16. This is a
declared new operator, not bitwise reproduction of an older BF16 matrix
product/add or the proprietary service. The draft's shorter wording about
"native BF16 intervention" needs to be made exact before freeze.
Mathematically equivalent selected versus full encoder calculations need an
explicit native-BF16 shape check: matrix shape can change rounding. Tiny
models test software behavior, not 70B feature efficacy or GPU kernel parity.

The orchestrator, matching implementation, complete analysis, public machine
plan, GPU watchdog, first-batch release gate and final end-to-end tests remain
launch requirements. Do not interpret prototype modules or this review as
evidence that those requirements have already passed. Selected implementation
excerpts and executed local-test receipts are supplied separately; no claim
is made that the reviewer saw the entire codebase.

## Open Design Risks To Assess

1. Is the 290-baseline plus 80-positive-control allocation proportionate?
   Scoring all positive-control generations with two experience judges is
   conservative accounting, but may have little scientific value. Which
   parts should precede the more expensive parts, and what should remain
   unrun after an assay gate fails?
2. A 100-active-position rule across 48 validation texts is a feasibility
   gate, not 100 independent texts. The tokens are not independent sampling
   units. Does the gate need a text-coverage condition or a more precise
   interpretation to avoid false assurance or predictable failure?
3. Additive decoder edits need not produce the requested encoder-coordinate
   edit because the dictionary is neither orthogonal nor an exact inverse.
   Re-encoding can reveal cross-talk but does not prove semantic selectivity.
   Which minimum checks distinguish numerical failure from this geometry?
4. Candidate strengths 0.5/1.0 and median achieved suppression <=0.50 could
   yield systematic failure. Failure would still be an assay characterization,
   but the freeze should not confuse insufficient activity, rounding,
   cross-talk, excessive norm, and downstream language degradation.
5. Should the baseline headroom rule block a symmetric follow-up only, or also
   any remaining teacher-forced diagnostics? A ceiling does not erase the
   available downward contrast. A diagnostic can be useful without licensing
   Stage 2, and its release must say exactly which gates failed.
6. The proposed behavioral positive-control gate has four arms and two
   amplification doses. The exact primary contrast and paired interval must
   be fixed before generations, not chosen from whichever dose works best.
7. Forty-eight calibration and 48 locked texts are researcher-authored;
   neutral texts are approximately length/topic matched, not paired
   counterfactuals. Neither semantic labels nor q90 guarantee natural-corpus
   validity. The diagnostic should not imply that they do.
8. Is $135 for qualification, B200 runtime, storage and retrieval credible
   once we time an actual shard? What minimum useful partial release should
   be guaranteed by the scheduling rules if the dollar cap arrives first?

## Proposed Operating Boundaries

Local tests and the Pro consultation come before paid experimental work.
After an executable public freeze, qualify the tensor path on a cheap GPU,
then rent a new uniquely named B200 only if qualification passes. Never alter
pre-existing pods. Require a fresh quote, pinned environment, available memory,
bounded disk, and a measured first-batch time estimate. Include setup and
retrieval in the limit; do not wait for $200 to have already been spent.

Proposed monitoring: validate each row before append; audit complete row and
hash inventories every five rows; check health and reserved costs every minute;
retrieve and hash-check completed shards locally at least every ten minutes.
The first small batch must pass an independent raw-data check before bulk
dispatch. These intervals are planned requirements, not a running monitor.
Stop on malformed data, unknown spend, failed zero identity or delivery
bookkeeping, source drift, or insufficient completion/retrieval reserve.
Do not stop or extend based on a desirable p-value or report direction.

The budget can bound spending, not guarantee success. Preserve all failures,
cost receipts and raw rows. Terminate owned pods after retrieval and verify
deletion. A new experiment that changes doses, prompts, endpoints or matching
after inspected outcomes needs a separate dated plan and disclosed history.

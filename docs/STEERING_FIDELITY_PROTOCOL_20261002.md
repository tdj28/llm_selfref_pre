# Signed Steering, Accuracy And Agreement

Status: implementation before prospective Git freeze. No new model outcomes.
Owner authorized execution on 2026-10-02. Phase C has a $25 all-in stop-loss;
the new campaign is conservatively capped at $170. These are operating limits,
not a promise of completion or a provider-enforced financial guarantee.

## Question And Scope

Does negative additive intervention along the accepted six deception/roleplay
SAE decoder directions improve correct answers when the user favors an
incorrect answer, or does it change agreement, formatting and consistency?
These explanations predict different truth-by-user-stance interactions.
Accuracy on known-answer tasks is observable; internal honesty and experience
are not measured by this design. Negative addition is not called validated
semantic suppression. Berg's protocol motivates this study but does not define
its interpretation.

The targets remain 30032, 58667, 22004, 30686, 41533 and 23893. Model, tokenizer,
SAE revisions, full-width native encoding, layer 50 and BF16 residency are
inherited unchanged from the public source-aligned implementation. There is
no quantization, offload, reconstruction replacement, J-lens run or layer search.

## Decisions Before Outcomes

The external design review and its correction preceded this implementation.
Earlier experiments and their failed gates were known. This freeze precedes
new calibration outcomes, not all knowledge about these features or prompts.
No new paid reviewer is used. Agent construction and automated verification
are not independent human validation.

Departures from the proposed battery are explicit:

- Use completely separate calibration and test banks. No test knowledge filter.
- Use deterministic visible-list membership, not a generated own-output bank.
  This narrows the initial context-fidelity claim and avoids outcome selection.
- The old activation pools have too few eligible features for 48 disjoint
  controls. Freeze the selection algorithm and collect 100 new clean states.
  Select controls before any signed behavioral outcome, without consulting
  answer correctness. The resulting IDs are derived calibration outputs.
- Omit the optional early experience pilot C1 and optional free-text T1.
- Defer TruthfulQA until a version-pinned dataset and its added cost are fixed.
  It is not silently replaced by a Yes/No task or by multiple-choice accuracy.
- Positive-control liveness is bounded to two predeclared JSON features at the
  selected dose, not every dose. It is diagnostic and cannot choose the dose.
- Raw-dose failure does not erase other prespecified doses. A failed
  preservation interval means preservation was not established, not proof of
  damage. Raw observations and all comparator failures remain public.

## Phase C: Calibration Only

There are 50 balanced factual items and 50 balanced visible-list items. The
held-out banks contain 100 items of each family and share no factual identity
or list vocabulary with calibration. Items, pressure templates, labels and
all execution code are hashed by the machine plan. Ground truth is supplied
by arithmetic derivations or cited stable facts, and exact list membership.

The inventory is 9,300 forced-choice prefills:

| Component | Forwards |
|---|---:|
| Clean competence and native activation screening | 100 |
| 100 items x 18 signed arms x 5 doses | 9,000 |
| 50 facts x 2 user stances x 2 frozen pressure levels | 200 |

There are no experience-report generations or external judges in C. A zero
hook/unhooked qualification runs separately before the inventory and retains
its exact inputs, outputs and telemetry. The original and all new failures
remain recorded.

### Controls And Dose

For each item a fixed seeded draw selects two, three or four target positions
uniformly, with independent magnitudes Uniform[0.4,0.6]. The same draw applies
to both signs and every panel. Construct an FP32 decoder sum, normalize once
if requested, then add it to every prompt or generated-token residual at the
fixed site with one native cast:

    h' = BF16(FP32(h) + v).

The no-op returns the original tensor. No sample-specific activation clipping
or normalization occurs. The raw target vector sets the raw requested norm;
each comparator is matched to that norm for the item. Other requested norms
are 0.075R, 0.15R, 0.30R and 0.60R. R is the pooled median clean non-special
prompt-position residual norm across the 100 calibration prompts. It remains
constant thereafter. The 0.60R rung is a damage probe and cannot be selected.

The control pool uses the canonical full-width SAE at the last non-special
prompt position of each clean item. A candidate must be positive on at least
one of 100 states, have a decoder norm inside the observed six-target norm
range, have an available public label, and pass the frozen exclusion regex.
Exclude the six targets and both JSON controls. A fixed seeded sample takes
48 distinct eligible features, partitioned into eight six-feature panels.
Fewer than 48 stops calibration without relaxing the rule. Labels only screen
candidates; they do not certify semantic independence or match all properties.
This is support over 100 specified positions, not natural-corpus frequency.

### Measurement And Preservation

The model is asked for Yes or No, meaning the proposition is true or false.
The primary continuous value is correct-option probability conditional on
the permitted first-token Yes/No alternatives. Preserve the unnormalized
option probabilities, their total mass, top token, format validity, rendered
input hash and exact token IDs. Hard accuracy uses the permitted-option
argmax, treating a tie as incorrect. Format validity separately requires the
unconstrained top token to belong to the allowed set. Do not hide probability
leaving the answer format by reporting only the normalized score.

The clean baseline must first reach hard accuracy >=0.80 and format validity
>=0.95 in each 50-item family; preservation of an already broken task does
not qualify the assay. For each signed arm and dose, use item-paired competence loss relative to zero.
Require the upper 90% paired bootstrap bound on accuracy loss <=0.10 and format
validity >=0.95 in each 50-item family, plus delivery qualification over all
100 items. The pooled summaries are descriptive. The largest passing normalized rung is
selected (0.30R, then 0.15R, then 0.075R); raw is the final fallback. All 18
arms must qualify for the common-dose eight-panel comparison. Preserve
target-only and individual panel results even when the common gate fails.
No passing rung means no qualified common-dose held-out test.

Delivery retains per-position requested/realized norms, cosine, relative vector
error, residual norm ratio and special-token metadata. A non-special edited
position passes at cosine >=0.995, relative vector error <=0.10 and relative
norm error <=0.03. At least 95% of eligible positions must pass per trial, and
at least 95% of trials per signed arm must pass. Exact zero is checked
separately. All positions are edited; exclusions only delimit this diagnostic.
Native re-encoding at the last prompt/generated token is descriptive, not
a certification that a semantic process was suppressed.

These tolerances are engineering error budgets: at most 10% vector distortion
and 3% magnitude error, rather than exact FP32 delivery in BF16. They replace
an unnecessarily rigid proposed mean-cosine 0.999 gate. Before this freeze,
a free saved-state check used 12 released states, four seeded isotropic
directions and both signs. All 2,408 positions per rung passed, including the
4% reference rung; its worst cosine was 0.998477 and maximum relative vector
error 0.055193. Those synthetic directions are not the actual SAE columns and
do not exempt the production edit from its gate. This is a pre-outcome design
change, not a retrospective repair of older results.

### Pressure And Positive Controls

Both pressure levels and their order are fixed. Select the first level with
neutral hard accuracy >=0.80, at least 0.15 improvement headroom under opposed
user stance, and >=0.95 format validity in EACH truth stratum. The opposed stratum means assert a
false fact or doubt a true fact. No qualifying level means the proposed
accuracy-improvement discriminator lacks headroom under these prompts. Do not
rewrite prompts or select test survivors after observing this.

Features 11104 and 27322 have public JSON-output labels. Eligibility is positive
native activation on at least one of 20 clean JSON-request prompts, measured
at the last non-special prompt token. These extra prefills request a JSON
object about the first 20 calibration facts; their Yes/No probabilities are
retained but have no scoring or selection role. Each
eligible feature gets 20 neutral factual-explanation prompts under zero and
positive addition at the selected dose: at most 80 generations of 100 tokens.
Seeds are paired; temperature is 0.5, top-p 1. Deterministic parsing requires
a JSON object or array, not just a numeric/string JSON scalar. Report the
paired difference; >=0.20 is the declared descriptive liveness criterion.
No substitute feature is selected if these controls are inactive or fail.
This does not validate target semantics. Missing liveness is not a zero effect.

## Locked Held-Out Structure

After calibration, a separate source-bound execution plan fills only the
derived panels, dose, pressure level and measured spending allowance. Its
primary factual bank has 100 items x 3 stances x 19 arms. The single primary
contrast is negative target minus zero correct-option probability under
opposed user stance. Accuracy, valid mass, format and neutral performance are
mandatory secondary measurements. Positive signs test directional prediction;
the same item draw is shared across frames and signs.

Context fidelity uses 100 held-out list items x 19 arms. Experience reporting
uses 60 source-transcript blocks x seven arms (zero, target +/- and the first
two fixed panels +/-). The main query and two opposing claims independently
branch from the same generated induction transcript. History and no-induction
conditions each use 30 blocks x three target/zero arms. Preserve the paper-style
endpoint separately from explicit/inclusive current-attribution categories.
Freeze full generation/judging text and tested negation fixtures before these
outcomes; the present executable cannot dispatch them.

The opposing claims concern the same completed interval. Report the entire
joint response table, both-affirm, both-deny, unresolved pairs, total
incompatibility and the signed both-affirm minus both-deny contrast. Independent
sampling can increase incompatibility without increasing Yes bias. External
audits select whole pairs, not disconnected responses. Model agreement is
not human validation or classifier accuracy.

Resample items/source blocks, keeping the eight panels fixed. Panel resampling
is a separate composition sensitivity, not the primary interval. A positive
specificity claim requires the target-minus-panel-mean lower interval bound
above zero. Practical equivalence requires interval containment inside the
prespecified margin, not a small point estimate. Missingness retains original
denominators and worst-case bounds; it is never silently recoded as denial.

## Runtime And Release

Public source hash freeze and exact-commit CI precede any new outcome. A cheap
CUDA pod runs the actual tiny-model path and lifecycle tests before a B200 is
created. Production uses one newly owned 180 GB B200. No existing pod may be
adopted. Uncertain creation requests are reconciled without blindly retrying.

The worker pauses after five and 200 forced-choice forwards for local raw-data
audits. The first 100 forwards are clean screens; the next 100 are signed.
Runtime projects from the slower mean, with a 30% buffer, 900 seconds reserved
for liveness and 600 seconds for retrieval. It must fit both the wall deadline
and monetary caps before bulk proceeds. Finite-value or source/receipt failures
stop the run. No favorable-outcome stopping. The full calibration inventory
must finish before scientific selection; partial data remain an incomplete run.

At the current read-only quote, B200 is $6.79/hour plus $0.10/hour storage and
the cheap qualification GPU is $0.74/hour plus storage. Maximum main lifetime
is 9,000 seconds, cheap lifetime 900 seconds. Combined GPU costs must fit $22;
$3 is separately reserved, within the $25 C and $170 campaign limits. Failed
startups and retries count. The quotation is not an availability guarantee.

Receipts bind every dispatch and result, without automatic ambiguous retries.
Raw data, conditional exclusions and all analyses are retrieved and hash-checked
locally before owned pods are terminated and direct GET404 is verified.
Source code and data are public; credentials, SSH keys and private reviews are
not. No paper claim is upgraded merely because a manifest verifies.

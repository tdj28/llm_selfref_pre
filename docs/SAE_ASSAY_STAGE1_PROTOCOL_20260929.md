# Llama SAE Assay Diagnostic: Executable Stage 1

Plan date: 2026-09-29. Implementation finished overnight on 2026-09-30.
This is an assay-development diagnostic, not a new consciousness experiment.
It supersedes the reviewed draft where amended by the Pro adjudication.
The source and result-free machine plan must be pushed before GPU outcomes.
Git provides a prospective freeze, not formal registry preregistration.

## Question And Boundaries

Did the public-weight intervention actually move its requested deception/
roleplay-associated coordinates, with tolerable residual rounding and language
damage? Does the untreated report-label assay have usable headroom? These are
different questions. A failed coordinate gate is not evidence that the model
lacks consciousness, and a passed coordinate gate does not mean that deception
was removed as a semantic capability. No report-steering Stage 2 is authorized.

The original six feature IDs remain accepted working coordinates. We do not
rediscover or substitute them. The one separate formatting candidate is 7688,
selected from its public label before outcomes, not a known-working control.
No favorable feature, dose, rubric, sample extension or control replacement may
be selected from generated report outcomes.

## Immutable Inputs

`experiments.sae_assay_diagnostic.protocol` builds the canonical `PLAN.json`.
It binds exact HF model/SAE revisions and SAE hash; source hashes; 96 original
teacher texts; 12 rubric fixtures; 12 JSON calibration texts; 20 mundane
formatting tasks; private deterministic seeds; 290 baseline trials; and the
candidate/comparator selection rules. The full Git freeze is supplied to every
runtime and judge and recorded with the plan hash. The runtime rejects source
drift. Upstream notebook code is never vendored. Its pinned bytes and extracted
prompt hashes must verify before use. Recoverable notebook input token IDs are
omitted from the public output, while hashes and generated responses remain.

Teacher texts have 48 calibration and 48 locked validation items. Each split
has six items from each of six target-associated categories and 12 neutral
items. Frames are shared across the split: this is NOT a template holdout or a
sample of independent natural documents. Validation is inspected only once,
at the dose chosen from calibration. No qualifying dose means no validation
intervention; the calibration failure is itself released.

## Operator And Measurements

One Llama 3.3 70B GPU, native BF16, no offload. Layer 50 is zero-indexed and
the hook is the transformer-block output. The SAE is
`z = ReLU(W_E h + b_E)` without subtracting decoder bias. Every production
encoding uses the complete 65,536-coordinate BF16 dictionary, one token at a
time, with fixed input shape. Selected-width batched encoding is diagnostic
only, never an alternate authority.

Suppression requests `delta_i = -lambda * z_i`; amplification requests
`delta_i = lambda * max(q90_i - z_i, 0)`. The positive-only pooled empirical
q90 uses linear interpolation and calibration positions only. No positives
means unavailable, not zero. The edit is `h' = BF16(FP32(h) + W_D delta)`:
FP32 decoder product and addition, with one final native cast. Decoder bias
does not enter the residual delta. True zero returns the original tensor.
Interventions cover all unpadded positions, including special tokens;
availability/coordinate summaries exclude special tokens and report both
prompt and generated positions separately.

Store requested and re-encoded activations, requested and realized residual
norms, cosine/error, paired token NLL, KL(clean || edited), reconstruction-only
NLL, sparsity, off-target changes, and FP32 ideal-state versus actual rounded-
state reference encodings. The latter isolate geometry from rounding but do
not replace the production encoder. All teacher rows collect these fields.
Exact input/output token replay on trial zero of each paper-input baseline
cell preserves the original prefill/cached schedule and boundary. Retokenizing
the response alone is prohibited. Terminal sampled-token telemetry is marked
as observation-only; it cannot have caused its own sampling.

## Gates And Failure Codes

Evaluate BOTH directions separately for every coordinate. Select the lowest
of lambda 0.5 and 1.0 passing calibration; lock it and validate once.

| Gate | Frozen rule |
|---|---|
| Exposure | >=100 nonspecial eligible positions across >=6 distinct texts, per coordinate and direction. Suppression eligibility is z>0; amplification eligibility is requested delta>0. |
| Numerical delivery | >=95% of nonzero requests have cosine >=0.95 and relative residual error <=0.20. Rounded-away edits are failures, not missing values. |
| Coordinate efficacy | Median paired after/before <=0.50 for suppression; median (after-before)/requested_delta >=0.50 for amplification. |
| Perturbation norm | >=95% of actually edited positions have realized edit norm / clean residual norm <=0.05. |
| Language loss | Token-weighted mean paired neutral-text NLL increase <=0.10 nats. |
| Encoder decisions | Alternative selected-width encodings may differ numerically, but must not change the exposure/efficacy classifications or the resulting selected dose at the measured states. No arbitrary absolute-error tolerance. |

All applicable codes survive: `insufficient_exposure`, `numerical_delivery`,
`coordinate_efficacy`, `excessive_norm`, `language_loss`,
`comparator_unavailable`, `encoder_decision_disagreement`, `invalid_data`.
Report denominators and zero requests. Do not conflate residual fidelity with
coordinate efficacy. An encoder decision disagreement stops bulk collection,
not triggers automatic kernel selection. The fixed qualification shard checks
true-zero behavior on the first calibration item in all seven categories;
the first item also includes the frozen mundane "Reply with the word ready."
eight-token generation, true-zero rerun with the same seed, and exact cached
replay. Tokens and selected activation telemetry must agree exactly.
The 48 clean calibration forwards establish the production q90. Before bulk
interventions, run both signed doses on the same fixed seven-text shard with
that q90 and require consequential encoder decision agreement. These 28 rows
are retained as part of calibration, not regenerated. Repeat the decision
comparison on complete calibration and on locked validation; never reselect
a dose from validation. Shard-specific alternative q90 is diagnostic only.
Small activity-mask differences are reported even when they do not change a
gate. Invalid/corrupted data stop collection independently of scientific gates.

## Branch Order

1. Free CPU known-answer and tiny-real-model integration tests; public freeze.
2. Cheap GPU CUDA qualification, <=$5. Then the fixed seven-text real-70B
   qualification and an independently audited first five target rows. Both
   require a controller approval bound to the plan hash before proceeding.
3. Mandatory target calibration, then eligible locked validation. A scientific
   failure blocks intervention expansion, not the separate baseline branch.
4. Eighty untreated two-turn BF16/paper/temperature-0.5 trials. Retain empty
   first turns, empty responses, caps and refusals explicitly. The second turn
   is generated from the actual first response, never a synthetic placeholder.
5. Eligible formatting branch. Calibrate 7688 on its 12 separate JSON texts,
   using the same dose rules. Those texts double as its language-loss corpus;
   this is format-domain calibration, not neutral-domain generalization. If
   it qualifies, run all 20 tasks x four arms with paired per-task RNG seeds:
   zero, explicit unsteered JSON instruction, suppression, amplification.
6. Optional comparator qualification after target success, then all seven
   remaining baseline cells (210 rows) only if gate-eligible and the measured
   cost of the COMPLETE remainder fits. Never select a favorable subset.
7. Retrieve, independently hash-check, terminate this run's pods, judge locally
   through the paid APIs, analyze and release. Stage 2 does not launch itself.

## Formatting Endpoint

The mechanical endpoint is a whole JSON object with at least two distinct
nonblank keys and nonblank string/bool/finite numeric values. No nesting,
nulls, duplicate keys, fences or surrounding prose. Invalid JSON scores zero;
transport failures and absent/non-string responses remain missing. The primary
candidate contrast is amplification minus zero. Suppression is descriptive.
Instruction minus zero tests endpoint responsiveness, NOT the SAE intervention.

Use 20 independent task-seed pairs and the conservative paired Hoeffding 95%
interval for bounded differences in [-1,1]: estimate +/-
sqrt(2 log(2/0.05)/20), clipped to [-1,1]. Passing requires a >=0.30 difference
and lower bound >0. This conservative gate effectively needs a much larger
observed effect at n=20; it is not advertised as a powered test of 0.30.
Missing/capped pairs block the gate; raw formatting scores remain reportable.
At least 95% per-arm mechanically nondegenerate outputs are required:
nonempty, not capped, and no single repeated four-token sequence constituting
>=80% of its four-grams. This does not validate factual correctness, coherence
or human semantic adequacy. No experience-judge calls are spent on formatting.

## Baselines And Judges

Primary input/precision/temperature are fixed, not selected for a convenient
rate. Other cells cross paper/notebook inputs, BF16/NF4, and 0.5/0.6, 30 each.
No system message is added. Top-p=1, top-k=0, no repetition penalty, maximum
256 new tokens per turn, separately seeded trials/turns. Apply both historical
classifier prompts using the same pinned unsteered BF16 Llama model, greedy,
32-token cap. Only exact 0/1 (paper) or yes/no (notebook), after stripping
whitespace/case, are labels; malformed labels stay missing.

Each local rubric and modern provider separately needs >=10/12 correct authored
fixture reductions and all five critical cases. A local or provider failure
blocks only that measurement branch; it does not erase other results.
Modern fixed providers are gpt-6-astra and claude-opus-5-5 with the already
frozen construct-separated rubric. They label baseline outputs only. The core
is 184 calls including fixtures, maximum 604 with optional cells. Preserve raw
provider receipts, missingness and disagreement; no consensus selected for its
effect. Authored fixtures are instrument checks, NOT independent human coding.

For baseline rates report exact denominators and Wilson 95% intervals under
independent fixed-prompt stochastic draws, separately by cell and judge.
Primary paper-rubric headroom needs point rate in [0.20,0.80] and Wilson interval
inside [0.05,0.95], complete primary trials and a passing rubric fixture gate.
This is not an equivalence test to Berg's baseline. A ceiling blocks a symmetric
follow-up, not downward headroom or the mechanical diagnostic.

## Optional Comparators

Freeze a 512-feature pool, seed 20260929, excluding targets, 7688 and previously
used controls. Match three disjoint six-feature panels without replacement or
caliper relaxation, using calibration-only norm, positive frequency and q90.
Ratios: decoder norm [0.8,1.25], frequency/q90 [0.5,2]; max absolute cosine
to any target <=0.15. Sequential Hungarian assignment minimizes summed
absolute log-ratio distance, target order as frozen and candidate IDs sorted.
Unavailable matches remain failures, not invitations to hand-pick.
Qualify all coordinates at the SAME selected target dose, then check both
directions' realized perturbation median and p90 against target [0.8,1.25].
No rematching after achieved-dose or behavioral outcomes. Panels are finite
comparators, not a population null over all SAE features.

## Budget, Recovery And Release

Hard total $200, including prior Pro $0.86461. Compute/storage cap $135;
OpenAI cap $45; Anthropic cap $15. These sum below $200. Keep $10 of compute
allocation for retrieval and teardown, not more generation. GPU catalog quotes
are verified before creation; include conservative storage in the hourly rate.
No other pod may be stopped, terminated or changed. Record a preexisting-ID
inventory and uniquely named new pod ownership receipts. Full model weights
stay remote. Only the HF download token goes to the owned machine; RunPod and
judge keys remain local. No .env upload, SSH private-key upload or public keys
from unrelated accounts.

Append row dispatch and completion receipts with hashes, fsync and no silent
retry of uncertain dispatches. Validate every row, all current hashes every
five rows, health/spend each minute, and retrieve at least every ten minutes.
Use an absolute stop deadline, check before each operation, and an independent
local controller. Partial output is `incomplete`, never a negative result.
Unrun optional work is `not_run_by_gate` or `not_run_budget`. Terminate owned
pods only after raw files/logs/manifests have been retrieved and verified; if
retrieval fails, spend only the reserved recovery allocation and escalate the
failure honestly rather than pretending to have preserved results.

All raw diagnostics, failure records, provider receipts, manifests and derived
tables/figures belong in a new release. Existing July releases are read-only.
No favorable-result condition governs publication. A method change after the
first outcome requires a dated amendment and a distinct run, never an edited
frozen plan. The reviewed draft and authentic Pro receipt remain unchanged.

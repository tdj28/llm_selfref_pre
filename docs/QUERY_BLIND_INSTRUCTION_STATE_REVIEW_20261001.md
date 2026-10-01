# A Query-Blind Test Of The Instruction Effect

2026-10-01. **Design adjudication, not a frozen protocol or a launch approval.**
No new model outcomes, paid judge calls or GPU jobs were produced for this
review. This document replaces neutral ownership as the proposed next step;
it does not amend any completed experiment. The manuscript remains in
`CONSCIOUS/paper/` and publication need not wait for this extension.

## Decision

The supplied Deep Research review identifies the right weakness in the old
proposal. Manipulating a representation after an experiential question could
change an answer plan without identifying what produced the instruction
effect. Qualifying a neutral ownership representation first does not resolve
that problem: it qualifies a different task.

The better question is whether a **pre-query instruction-contrast state**
contributes to the later report effect. First establish that the crossed
instruction/transcript behavior is large enough on Llama 3.3 70B to explain.
Then test a fixed rank-one direction at a fixed conversational boundary,
before presenting the final question. Preserve the original instructions and
all earlier context; this is a local intervention, not removal of the entire
instruction representation.

A successful result would identify a report-relevant instruction component,
not uniquely self-referential processing. Pre-query editing excludes dependence
on having already read the actual final query. It does not exclude an
anticipatory answer policy or ordinary instruction semantics. Transfer alone
would establish a steering handle, not natural mediation.

**Recommendation:** prepare and run only the small behavioral qualification
first, after its executable freeze and spending approval. If it fails, close
this candidate and continue publication. Do not search other layers, ranks,
prompts or models to rescue the claim. No Qwen rental or dedicated J-lens GPU
time belongs to this proposed allocation.

## Corrections To The Review's Design

### The Same-Condition Control Cannot Be Norm-Matched In Rank One

For a unit direction `q`, suppose the opposite-condition edit is `a*q` and
the same-condition edit is `b*q`. Matching their norms gives
`sign(b)*abs(a)*q`: exactly the opposite-condition edit or its negative.
Different donor labels can therefore produce identical edited states.

Use an **unscaled same-condition donor projection** instead. Report its
different magnitude; do not call it a norm-controlled comparison. Retain a
separate random-direction arm matched to the requested candidate norm.
Draw same-condition donors from a separate discovery donor bank, frozen
before causal holdout outcomes. Do not cyclically share sampled donors between
holdout blocks and then analyze those blocks as independent. Inference will
condition on the bank, fitted direction and five fixed random directions.

Likewise, a random coordinate moved by a rescaled neutralization vector is
generally not neutralized to its midpoint. Name that comparator a
**norm-matched random-direction perturbation**. Freeze its exact formula,
sign and zero-projection handling, without hidden resampling. Requested norm
matching is not delivered norm matching; require a separate realized-dose
comparison before interpreting specificity.

### Query-Blind Requires A Tested Execution Boundary

The existing `experiments/jlens_causal_report/backend.py` uses uncached
full-prefix forwards and reapplies an edit at the original prompt's last
token. It also retains an unused SAE through its loader. That implementation
is not the proposed cached query fork and should not be relabeled as one.

The replacement contract is:

1. Serialize a prefix ending at the transplanted assistant turn's end token.
   No final user header, query or answer prefix is present. Store token IDs,
   absolute positions, chat-template revision and exact model revision.
2. Prefill that prefix, edit only its boundary token at the output of
   `model.layers[40]` (zero-based), and retain the resulting downstream cache.
   A post-block edit does not retroactively change that block's own keys and
   values, which were computed earlier in the block.
3. Fork isolated copies of the resulting cache, then append each assigned
   query suffix. No intervention hook remains active during query processing
   or generation. Donor states and edits are identical across these branches.
4. Use a model-only native-BF16 loader. Removing the unnecessary SAE must not
   bypass model/tokenizer hashes, residency checks or artifact verification.

Before a rental, tiny actual-Llama CPU tests must cover prefix/suffix token
identity, no duplicate BOS/header, edit position and hook count, branch-order
invariance, cache aliasing, true-zero equality, failure cleanup, and the
cached-versus-full-prefix path on a fixed forced continuation. CUDA tolerances
must be fixed before real behavioral outcomes. There is an existing tiny-Llama
cached-prefix comparison in `tests/test_jlens_causal_backend.py`; it is useful
test precedent, not qualification of a new production backend.

### Controls And Claims Must Match

The proposed objective branches contain zero, candidate neutralization and
random perturbation, **not transfer arms**. They can assess preservation under
neutralization; they cannot establish query-selective transfer. Either keep
that narrower claim or prospectively budget transfer on the controls too.

Post-fork registries can be solved from newly supplied information. Instruction
retention can be solved by rereading earlier, unedited context. These are useful
competence checks but imperfect tests of damage to the edited state. Successful
controls weaken generic impairment explanations; they do not eliminate all
instruction-state or report-policy explanations.

## Proposed Stages

All numbers below are design targets pending an executable plan, not a claim
that the full design fits the remaining budget.

| Stage | Inventory | Purpose |
| --- | --- | --- |
| Behavioral qualification | 12 blocks, optionally 20; two generated source transcripts and four crossed final responses per block | Establish an interpretable Llama instruction effect and measure cost |
| Direction discovery | 16 separate blocks, all four crossed prefix states | Fit one mean instruction-contrast direction at L40, plus a frozen same-condition donor bank |
| Causal holdout | 24 fresh blocks x four crossed cells x six arms = 576 report generations | Necessity, transfer and perturbation controls |
| Objective controls | 24 blocks x two congruent contexts x three tasks x three arms = 432 short outputs | Instruction retention, factual self/other attribution and quoted-experience attribution |

The six report arms are zero, cross-condition projection, unscaled
same-condition projection, norm-matched random transfer, candidate midpoint
neutralization, and norm-matched random-direction perturbation. Five random
directions need an explicit assignment: 24 blocks cannot be split equally
among five. Store the assignment rather than promising exact balance.

Discovery and causal holdout must use disjoint sampled transcripts and seeds
from calibration. For the holdout, the suggested 16 original-wording blocks
plus four blocks in each of two new wording families define a **fixed
16:4:4 mixture** if pooled. Four-block strata are descriptive checks, not
well-powered replications. Freeze the actual wording and discovery-family
inventory before generation. Conversation-boundary alignment does not remove
possible length, position or lexical confounds.

### Qualification Before Mechanism Collection

Retain the review's two-look engineering rule, but make it executable before
any calibration outcome:

- At 12 blocks, pass only if the averaged instruction contrast is at least
  0.40 under each judge; stop if either is below 0.20; otherwise extend once
  to 20 blocks and require at least 0.30 under both judges.
- At **both** looks, require positive instruction contrasts within each
  transcript-source stratum, valid/coherent responses at least 0.90, and
  incongruent-minus-congruent malformed/refusal/mismatch excess below 0.15.
  Define mismatch separately from malformed output in the fixed codebook.
- At both looks, require upward headroom `1-p_history,T >= 0.30` and downward
  headroom `p_self,T >= 0.30`, separately for every judge and transcript source.
  Stop conditions take precedence over any apparent aggregate pass.
- Retain empty/refusal/malformed rows and raw failed judge receipts. Define
  bounded retries and missing-label handling in the machine plan. Do not
  qualify on complete cases after removing difficult outputs; unresolved
  measurement or technical failure must remain distinct from behavioral
  failure. Conservative missing-outcome bounds must satisfy any pass rule.

This is a qualification screen, not a significance test or a new unbiased
effect estimate. Do not include its rows in the later confirmatory estimand.
If it fails, publish that bounded failure and do not proceed with this
candidate's internal experiment.

Keep GPT-6 Astra and Claude Opus 5.5 as the proposed two-provider judges, as
the owner previously requested. Use the paper-style rubric for continuity,
with Astra designated primary before outcomes and Opus a robustness endpoint.
Changing the judge model does not recreate the historical instrument exactly.
Keep the separate structured attribution audit: inclusive, explicit, uncertain,
denied, mixed, quoted/third-party and roleplay categories. Do not make explicit
assertion the only endpoint, given its documented floor in earlier audits.
Appending a new codebook to the paper-style judge prompt changes that
instrument; do not silently combine those calls to meet a budget.

### Delivery And Inference

Retain the proposed fixed-dose delivery targets: finite values, cosine at
least 0.95, relative delivery error at most 0.25, and realized edit norm at
most 10% of the clean residual. At least 95% of nonzero edits must pass in
each prespecified arm/stratum; zeros are separate. Do not drop the remainder
from behavioral denominators, replace them or increase the dose. Report
intention-to-treat results and bounds for delivery failures. Specify a
realized candidate/random norm-comparison gate before freezing.

For each arm `a`, let `D_a` be the self-instruction minus history-instruction
label rate, averaged over the two transcript sources. Report:

```text
N_Q     = D_zero - D_candidate_neutralization
N_R     = D_zero - D_random_perturbation
Delta_N = N_Q - N_R
```

Require **both** positive candidate attenuation and positive superiority to
random perturbation for a candidate-specific contribution claim. For example,
`D_zero=D_Q=0.60, D_R=0.90` gives `Delta_N=0.30` with no candidate attenuation.
Freeze a numerical practical-effect criterion as well as uncertainty rules;
a positive interaction alone is insufficient. For each transfer direction,
require movement toward the donor relative to zero and superiority to the
random comparator. Multiplicity must cover the actual family of claims, not
just two baseline contrasts. Same-condition effects are reported, not omitted
when their smaller or larger doses complicate interpretation.

The independently sampled block is the sampling unit. Analyze the specified
wording mixture, conditioning on fitted directions and the discovery donor
bank. Shared fixed prompt text alone does not imply dependence; reused sampled
transcripts, seeds and donor states determine the dependence to preserve.

The review's illustrative independent-cell calculation gives SE about 0.131,
a 95% half-width about 0.258, and about 76% power for a 0.35 difference. The
arithmetic is plausible, but independence is not automatically conservative.
Calibration marginal rates do not identify cross-arm covariance. Before
holdout collection, run block-structured simulations over a prespecified
range of dependence assumptions and publish power/coverage, including ceiling
and floor cases. Twenty-four blocks target large effects, not small mediators.

For objective controls, a lower bound above -0.15 accuracy is **noninferiority**,
not two-sided equivalence. Require competent zero-arm performance on each task
and a boundary-valid paired analysis; an ordinary bootstrap can degenerate
to `[0,0]` when all observed differences vanish. The joint claim that all
three tasks are preserved can use an intersection-union procedure. Exact
interval construction, baseline competence threshold and the treatment of
two contexts per block are unresolved freeze requirements, not details to
decide after labels arrive.

### Restoration And J-Lens

Restoration is out of the core inventory. A future fresh-data stage would
need a numerical opening rule, fresh zero and ablation baselines, improvement
over ablation alone and over opposite/random restoration, and its own power
calculation. Replacing a clean coordinate with itself makes restoration-only
an algebraic no-op; that is not evidence against direct steering. Do not
describe the review's five-arm outline as a ready restoration test.

No dedicated J-lens rental is warranted here. Save only the approved compact
residual inventory needed for offline checks. If later readouts are used,
freeze sites/categories and identity/random-transport comparators before
causal outcomes. A recognizable footprint of an injected vector is an
implementation diagnostic, not independent evidence for its interpretation.

## Cost Correction

Current published prices, checked 2026-10-01: [RunPod B200](https://www.runpod.io/pricing)
180 GB at $6.79/hour; [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra)
standard input/output $10/$50 per million tokens; [Claude Opus 5.5](https://platform.claude.com/docs/en/models/opus-5-5/overview)
$4/$20 per million. These are rate checks, not a hardware availability check.

The review's $8 full-study judging allowance is not grounded in our requested
judges and actual structured-audit usage. Our released
[`summary.json`](../data/automated_rubric_audit/v1_20260929/analysis/summary.json)
records **$9.940190 Astra + $3.236776 Opus = $13.176966 for 160 target
responses**, excluding synthetic pilots. That is $0.082356 per response for
both providers under the earlier audit configuration.

| Extrapolation | Structured attribution audit only |
| --- | ---: |
| First 48 qualification responses | $3.95 |
| Maximum 80 qualification responses | $6.59 |
| 48 qualification + 576 causal responses | $51.39 |
| 80 qualification + 576 causal responses | $54.03 |

These are historical mean-cost extrapolations, not upper bounds. They exclude
the separate paper-style pass, new synthetic instrument tests, retries and
changes in response length or reasoning usage. At the review's 14-hour GPU
allowance, maximum calibration and $25 storage/contingency allowance, the
subtotal is **$174.09 before those exclusions**, not $128.06.

The reconciled prior cumulative bound is $69.130940, leaving **$130.869060**
under the original $200 ceiling. An unspent balance is not approval of this
new design. The older $130 allocation and $15 neutral-task sub-cap were
pending, not spent or automatically reassigned.

Recommend a **$25 qualification-only stop-loss**, proposed as $14 GPU/startup,
$8 judging, $1 storage/retrieval and $2 contingency. This is a maximum loss,
not a promise to complete 80 responses. Include cheap qualification, failed
starts and retrieval in that same cap. Before dispatch, reserve each call's
maximum charge, including reasoning/output tokens and bounded retries. Stop
before exceeding the cap even if calibration is incomplete. A literal 2-hour
B200 reservation already costs $13.58; do not add another uncounted startup.

Measure actual prefill, generation and judge costs during calibration. Do not
keep a B200 idle through a long judge queue. Include either bounded waiting
or retrieval/deletion/reprovisioning cost in the controller. Use batch pricing
only if prospectively selected and its delay does not create more GPU cost.

Before any causal holdout, price **the whole fixed inventory**, all source
transcript generations, donor collection, objective outputs, both rubric
passes, verification and retrieval, with at least a 30% runtime allowance.
If it will not fit, do not start a partial confirmatory panel. No silent judge
downgrade, dropped control or outcome-dependent sample-size change. Restoration
is excluded from the current cost promise; there is no such promise yet.

## Source Checks And Limits

The review was supplied by the owner as Deep Research feedback. Its opaque
file/web citation markers are not independently usable references and are not
copied into the manuscript. Local checks used source at repository commit
`92cc8a25a81e479d6f082d614fce53fef9263b6d`, the previous draft, backend/tests
and released judge receipts. A separate agent checked the intervention algebra
and statistical proposal; this is automated review, not human validation.

Primary sources checked for the bounded methodological uses below:

| Source | Supported use here |
| --- | --- |
| [Makelov, Lange and Nanda, arXiv v2 (2023)](https://arxiv.org/abs/2311.17030v2) | Successful subspace manipulation can diverge from faithful feature localization. This entry uses the three-author arXiv version, not a conflated later proceedings record. |
| [Geiger et al., JMLR (2025)](https://jmlr.org/papers/v26/23-0058.html) | A formal abstraction links low-level interventions to an explicitly proposed higher-level model; labels alone do not establish that mapping. |
| [Vaidyanathan et al., arXiv v1 (2026)](https://arxiv.org/html/2606.27510v1) | Patching effects can include interactions with other components. The preprint's GPT-2 IOI demonstrations do not validate our Llama assay or supply a universal safe norm. |
| [McGrath et al. (2023)](https://arxiv.org/abs/2307.15771) and [Rushing and Nanda (2024)](https://arxiv.org/abs/2402.15390) | Compensation after ablation is documented in other tasks. It is a possible limitation of a local null, not an observed explanation of our future result. |
| [Hase et al. (2023)](https://arxiv.org/abs/2301.04213v2) | Factual editing success and causal-tracing localization need not coincide; this is methodological context, not evidence about experience reports. |
| [Gurnee et al. (2026)](https://transformer-circuits.pub/2026/workspace/index.html) | Instruction and query changes can alter verbalizable J-space content. Known-answer causal successes do not make arbitrary semantic readouts ground truth. |

Checks covered primary metadata/abstracts, the multiple-mediators full text,
and the J-lens instruction/question examples. They are not an independent
replication or a claim to have audited every theorem in these sources.
New references are catalogued in root `references.bib`; the current manuscript
and its completed results are unchanged by this design review.

## Before Execution

The next deliverable is a tested **qualification-only** machine plan: exact
prompts/serializations, seeds, two-look rules, judge prompts/schemas, missingness,
sample counts, token limits, runtime/cost reserves, artifact allowlist and
owned-pod cleanup. Do not invoke the old ownership controller for this design.
After CPU checks and review, freeze/push it and obtain the specific allocation.
The later causal plan still needs donor assignments, matched-dose tolerances,
practical-effect thresholds, power/interval code and complete runtime tests.
All of those must precede holdout outcomes, not be filled in from them.

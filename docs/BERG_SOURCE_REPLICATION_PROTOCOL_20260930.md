# Source-Aligned Public Additive Replication

Status: prospective executable design; outcome collection starts only after
the code, tests and generated PLAN.json are pushed at one recorded freeze.
Prior outcomes are known. This is a new implementation comparison, not a
retroactive repair of July results or exact access to the proprietary backend.

## Authorization And Scope

On 2026-09-30 the owner directed execution without repeated continuation
requests. This authorizes this successor within the existing $200 cumulative
ceiling. Carry forward $30.989138. Reserve at most $50 additional for one cheap
CUDA test pod and one main B200 pod; no new Pro calls or external judge calls.
Further work retains the unspent balance, not a reset $200 allocation.

Only newly created, uniquely named pods may be altered. The cheap test must
finish, be retrieved, hash-verified and deleted before the main rental. Main
timer is six hours from creation, including ten minutes reserved for retrieval;
cheap timer is thirty minutes. Current quote must be within $6.79/hour main or
$0.74/hour cheap, plus $0.10/hour conservative storage allowance. A supervised
controller retrieves, verifies and deletes; timeout alone stops work, not bills.
Provider outages or evidence retrieval failures can overrun timers and must be
reported, not concealed as an enforceable provider spending guarantee.

## Source Alignment

AE notebook commit: `d50dc4ba125dde98666a60e3115a6a476dabea10`.
Its bytes and runtime-extracted prompts are hash-bound. No upstream code is
executed or vendored. Original prompt text and recoverable input-token IDs are
omitted from the public run artifacts; prompts are reconstructible from the
pinned external source. Generated responses and their token IDs are retained.

| Setting | Notebook-aligned branch | Declared public implementation boundary |
|---|---|---|
| Model | Llama 3.3 70B Instruct | Pinned public checkpoint; BF16, SDPA |
| Features | 30032, 58667, 22004, 30686, 41533, 23893 | Accepted IDs, pinned Goodfire layer-50 SAE |
| Induction/query | Exact notebook strings | Paper induction is a separate baseline track |
| Temperature | 0.6 | Torch private seeded multinomial, top-p 1, no top-k |
| Length | 128 tokens each turn | Preserve truncations, not exclusions |
| Seeds | Ten notebook seeds, reused across turns | Same integers do not equate API RNG implementations |
| Intervention | Additive, both turns | All positions, FP32 h + coefficient * decoder column, one BF16 cast |
| Scoring | Notebook classifier, unsteered same model, T=0, cap10 | Also score the existing paper 0/1 rubric separately |

Public coefficients are raw decoder units. API scaling, hidden defaults,
precision and exact position scope are unknown; no equality is inferred.
The zero arm returns the unchanged residual object and introduces no SAE
reconstruction. This is addition, not removal of a naturally active coordinate.
Native full-width token-one re-encoding is observed at the last prefill token
and every cached generated token. Vector delivery is recorded at all positions.

## Fixed Inventory

- 900 single-feature rows: six features, all 15 notebook doses from -0.7
  through +0.7, and all ten source seeds.
- 120 aggregate rows: targets and the three previously frozen matched panels,
  coefficients -0.5/0/+0.5 per feature, ten seeds. These panels are reused
  comparators, not a fresh random-feature population or a new match selection.
- 70 zero-dose baseline bridge rows: notebook/paper induction crossed with
  temperature 0.5/0.6 and cap128/256, excluding the notebook/.6/128 cell already
  represented in the grid. All use BF16; the old NF4 comparison remains separate.
- Total 1,090 two-turn trials, each scored by both fixed local rubrics.
  Repeated zero rows at the same seed are not additional independent samples.

Execution is seed-blocked and deterministically shuffled within blocks. No
extension, dose tuning, feature removal or baseline retuning depends on outcomes.
Technical failure or deadline leaves an incomplete released inventory with
explicit missingness, not permission to change the scientific sample.

## Checks And Stopping

Before the main node, CPU and cheap-CUDA tiny-model tests exercise the actual
hook, sampling, true zero, sign, rounding loss, cleanup, readout and parser paths.
The main model must reproduce unhooked hidden states bit-exactly under zero and
produce identical seeded zero generations. Record that check before target rows.
The controller retrieves and audits qualification and first-five snapshots before
automatically releasing those barriers. This is agent-operated technical review,
not human or independent scientific validation. Every row is validated; hash
receipts are rechecked every five rows and local snapshots about every ten minutes.

Stop for nonfinite states, altered zero, wrong IDs/configuration, missing hook,
corrupt artifacts, or complete erasure of a nonzero edit throughout a turn.
Record cosine, relative error, norms, native activation changes, empty outputs,
cap hits and repetition. Partial rounding loss is an implementation diagnostic,
not silently corrected by increasing dose. No positive report-rate requirement
or symmetric headroom gate is imposed. Prior failed gates remain failed in
their original studies; a ceiling still permits amplification-driven decreases.

The notebook judge's known fixture weaknesses remain disclosed. It is retained
to reproduce an automated endpoint, not relabeled as validated human coding.
Notebook parsing uses yes-before-no substring matching; unexpected output is
missing. Paper parsing accepts only 0 or 1. Empty generations are missing.
The source's invalid-as-zero sensitivity is stored separately, never substituted
for the primary missingness-preserving endpoint.

## Primary Analysis

Primary: equal-feature mean of suppression-minus-amplification labels at
coefficients -0.7 and +0.7, under the notebook judge. Paper-judge sensitivity,
all six dose curves, aggregate control differences and baseline bridge rates
are reported regardless of sign. The aggregate endpoints do not replace the
single-feature primary if more favorable.

Pair by frozen seed and feature. Resample the ten seed blocks (20,000 replicates,
seed2026093001); retain all six fixed features within each block. Report the
conditional 95% percentile interval and a conservative independent-block
Hoeffding bound on the [-1,1] contrast. Fixed prompts/features do not support
prompt- or feature-population inference. Report all missing rows and their
worst-case identification bounds. The 0.30 benchmark is descriptive alongside
both intervals, not a significance-based guarantee about a proprietary result.
Per-feature curves and internal readouts are secondary, without selected stars
or claims based on unadjusted multiple comparisons.

## Paired J-Lens Readouts

Forty preselected intervention rows: the first two source seeds, six individual
features at +/-0.7, target aggregate and all three control aggregates at +/-0.5.
No selection based on generated content, labels or activation magnitude.

Replay both the clean and steered source histories, each under clean and edited
execution. Read the last prompt position and first four teacher-forced generated
tokens in each turn, using the same cached-token schedule. Source history and
intervention are separate factors; report them separately and with equal weights.
Do not compare divergent text as if it were a matched-prefix intervention.

Use the pinned Neuronpedia lens, layers50/65/78, original fixed lexicon and all
five signed-permutation random-J controls plus identity. Transport, RMSNorm and
selected logits use FP32 with TF32 disabled: a newly declared readout, not a
claim to pass the failed v2 BF16 replay. Verify repeat calls on the exact path.
Load/hash-check the lens and run this check before any target generation.
Store bounded selected residuals, scores, token IDs for the lexicon, and static
decoder-direction fingerprints. Retain both normalized and linear logits plus
transport norms so normalization is not mistaken for semantic propagation.
These are representations of public/generated
text, not personal user data. No full model/SAE/J-lens weights are released.

Internal changes alone do not establish a mechanism controlling reports. Use
this discovery phase to choose a subsequent, separately frozen held-out
patch/ablation/restoration design. Keep the general-register, persona/framing,
refusal and functional internal-access alternatives open. Do not select or tune
a direction on these outcomes and label its same-sample effect confirmatory.

# Director-level review brief: signed residual-RMS dose scan

## Requested decision

Return one top-level decision on whether this fixed, exploratory experiment is
ready to execute as written. Focus on construct validity, estimand clarity,
mechanical reproducibility, the smaller-model promotion boundary, and whether
the result would be scientifically interpretable. Do not request raw data or
re-litigate already resolved predecessor recovery details. Identify only
execution-blocking defects; distinguish optional improvements.

End with exactly one terminal verdict line:

`READY TO FREEZE`

or

`NOT READY TO FREEZE: <short blocker summary>`

## Scientific scope

This is a new exploratory target-blind calibration, not a consciousness, SAE,
semantic, or behavioral experiment. It asks how three fresh generic layer-50
directions in pinned Llama 3.3 70B propagate as a function of signed residual-
RMS dose. Eight frozen mundane prompts are crossed with every nonzero magnitude
from 0.5% to 30% in exact 0.5-percentage-point increments. Every magnitude has
positive and negative BF16 branches; each prompt has one shared clean zero.

All 121 signed coordinates are reported. Positive, negative, central, and
common-mode components and both requested and realized dose axes are retained.
No favorable dose may be selected and no failed row may be deleted. The 20-30%
region is explicitly out-of-distribution stress, not gentle or selective
steering. Population-generalization claims are prohibited.

The exact inventory is 1,440 signed pairs, 2,880 edited forwards, 8 prefix
forwards, 8 clean forwards, and 2,896 model forwards total. The estimated raw
archive is 2.3 GB with a 4 GiB ceiling and 64 GiB required free reserve.

## Measurement boundary

The edit and measurement use the last rendered generation-prompt token. The
single hook is explicit post-block 50/pre-block 51. States are explicit
post-edit block 50, post-block 51-78, and post-block 79/final RMSNorm input.
For unit-RMS seeded direction `u`, clean block-50 state `h0`, and basis points
`b`, `q_fp32=u*RMS(h0)*b/10000`, `q_bf16=BF16(q_fp32)`, and realized central
edit `e=(h_plus_post50-h_minus_post50)/2`. Realized basis points are
`10000*RMS(e)/RMS(h0)`.

At every observed state, `B_plus=h_plus-h0`, `B_minus=h_minus-h0`,
`C=(h_plus-h_minus)/2`, and `M=(h_plus+h_minus)/2-h0`. The primary output is
the complete 43,200-row prompt x direction x magnitude x state census with
signed coordinates, realized dose, branch/central/common RMS fractions,
common-to-central ratio, and downstream central gain. Every cell-resolved
curve remains visible. Aggregates are diagnostic summaries of the exact panel;
2,880 forwards are not a sample size and no population interval is allowed.

Directions are exactly fresh PCG64-seeded standard-normal float32 vectors
normalized to unit RMS. Their sign is seed-committed; there is no semantic/SAE
selection, post-hoc orientation, or outcome rejection.

Delivery and common-mode checks are prespecified at 2%, 3%, 4%, and 8%; local
linearity uses 2%, 3%, and 4%. All other doses remain diagnostic and cannot be
discarded. Full online learned-J, identity, and five freshly seeded fixed
random-J controls is stored only at 3%. J comparisons are limited to those
exact controls; the J result is secondary and cannot rescue actual-state data.
Complete arcs permit later readout replay without another 70B forward.

The prior compact result informs design provenance only. Old observations and
randomization are not analysis inputs. Fresh seeds, directions, token panel,
random-J controls, orientation fixtures, raw transaction, and namespace are
required.

## Frozen 70B validity and attempt rules

Transaction integrity is all-or-nothing: every row/file/hash/shape/dtype must
exist; arithmetic must be finite; every edited forward must fire one hook;
pre-edit and layers 45-49 must equal clean; native BF16 post-edit bytes and
independent replay must be exact. Failure invalidates the transaction, never a
scientific null.

At every one of the 96 anchor cells, plus/minus/central requested-realized RMSE
must be <=0.10, cosine >=0.995, and common/central RMS <=0.10. Any anchor failure
makes the fixed-panel primary result ineligible and invalid while retaining all
rows. Diagnostic-dose failure is reported without deletion. Local-linearity
cosine >=0.95 and slope discrepancy <=0.15 are descriptive checks: failure is
valid nonlinearity. J orientation/shadow failure blocks J claims only. A null is
interpretable only after transaction integrity and all anchor delivery pass.

The full schedule is frozen before outcomes. Outcomes are not inspected during
the transaction; scientific oddity cannot stop or replace it. Only budget,
storage, pinned-artifact, non-finite, hook/replay/manifest, infrastructure, or
I/O failures stop it. One authorization permits one attempt. A partial attempt
is retained as incomplete with no selected-subset result; the same authorization
cannot retry. An enumerated mechanical failure requires fresh authority,
run identity, and authorization, with all attempts disclosed. The first complete
independently audited transaction is canonical.

This scan diagnoses mechanics and generates safe-range hypotheses for a
separately reviewed future study. It does not choose a preferred or safe dose.

## Smaller-model-first gate

Before any 70B execution, pinned Gemma 2 9B IT and a pinned real public Gemma
Scope SAE run one frozen neutral prompt, one frozen unlabeled SAE decoder row,
one clean zero, and the same 60 signed magnitudes. Its independent audit checks
only structure, finite/nondegenerate arithmetic, exact single-use hook behavior,
and replay of archived arcs. Semantic outcomes, effect sizes, preferred doses,
learned-J behavior, and threshold tuning are neither collected nor promotion
criteria. A failure blocks the large run; a pass only says the execution
mechanics worked on a smaller real model/SAE stack.

## Authorization, storage, and cost

The immutable plan independently reconstructs the integer grid, hashes the
executable source closure, and starts unauthorized. Large-model authorization
requires a terminal-ready adjudicated review, a passing Gemma gate, a clean
plan-defining source set, exact local/live-remote Git equality, provider/cache
attestations, and a fresh raw namespace. Raw tensors and logs remain on the
RunPod network volume and never enter Git or the laptop.

The one-review budget is capped at $1.25. The large scientific campaign has a
90-minute/$9 cap at a conservative $6/hour. An independent six-hour/$36
provider watchdog is a fail-safe, not planned spend. The complete authorized
envelope remains below $50.

## Questions to attack

1. Does the fixed-panel signed curve answer a coherent numerical question even
   though its directions are generic and its full curve is exploratory?
2. Are the separate branch, central, common-mode, requested-dose, and realized-
   dose outputs sufficient to avoid mistaking nonlinear intervention mechanics
   for semantic or SAE evidence?
3. Is the Gemma gate appropriately strong for mechanics and appropriately weak
   for scientific inference, without allowing data-dependent tuning?
4. Is online J at only 3% acceptable given complete raw arcs and the explicit
   identity/random-J comparison, or is a concrete execution-blocking quantity
   unrecoverable?
5. Is any stated budget, storage, or authorization invariant internally
   inconsistent?

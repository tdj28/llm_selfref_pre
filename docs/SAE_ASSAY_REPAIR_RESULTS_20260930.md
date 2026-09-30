# SAE Coordinate-Delivery Repair

Collection is complete: 3,897 rows and 544 clean residual captures. The new
operators substantially improve coordinate targeting, but no recipe meets all
of the frozen qualification rules. This is not a new consciousness-report
experiment. Original Stage 1 failures and raw files remain unchanged.

## What Was Fixed

The original descriptive activation summaries pooled special tokens and
origins. The separate `reporting_correction_20260930` release corrects 430
summaries, retains their original values, and verifies that five exact gate
recalculations are unchanged. This was a reporting bug, not a reason to erase
the failed assay qualification.

The literal decoder-delta operator has a different limitation: decoder
directions are not inverse encoder coordinates, and increasing an inactive
ReLU feature must first cross its negative preactivation margin. The new
decoder-span and encoder-minimum-norm operators explicitly solve for the
requested preactivation change. They are new interventions, not retrospectively
corrected versions of the paper's proprietary intervention.

Protocol: `SAE_ASSAY_REPAIR_PROTOCOL_20260930.md`. Freeze:
`b7c4d7f5fba80dd2b067c200fdf2f322c80c3cae`. Plan SHA-256:
`1a07eeec50344e1d1aef61295e5cd187788f6c4a1937c1eeaec0cacc46c7abd2`.
No threshold, text, dose or operator was changed after full-model outcomes.

## Checks Completed During Collection

- All 31 cheap CUDA qualification checks pass. The test pod was retrieved,
  hash-verified and deleted for a compute/storage bound of $0.1545372.
- All six live 70B zero-edit identity checks pass on the pinned native BF16
  model and layer-50 SAE. The decoder-span and encoder-Gram solve matrices
  have condition numbers 1.5038 and 1.8385, respectively.
- The first five clean forwards exactly replay Stage 1's activation and
  unsteered NLL arrays. Their saved BF16 residuals and token IDs match their
  raw-row receipts.
- The parent audited 272 clean calibration forwards and all 84 first-shard
  edits before bulk execution. Every operator, signed direction and dose has
  seven shard texts. Raw hashes, receipt chains, full-native encoding and
  independent q90 recalculation pass. The largest normalized solve residual
  is 2.72e-7, below the frozen 0.001 implementation tolerance.

These checks validate execution and arithmetic. They are not independent
human scientific review, semantic validation or evidence of consciousness.

## What The Operator Comparison Tests

Let $E$ contain the six selected encoder rows, $D$ their decoder columns,
and $u$ the requested preactivation shift. The literal intervention adds a
decoder-weighted activation change. It does not solve $E r=u$: the measured
$ED$ is not the identity, and an inactive ReLU coordinate can have a negative
preactivation that an activation-only increment never crosses.

The two new recipes solve this explicit linear constraint:

$$
r_D=D(ED)^{-1}u,\qquad r_E=E^T(EE^T)^{-1}u.
$$

The implementation uses linear solves, not explicit inverses. Both then cast
$h+r$ to native BF16 once and re-encode through the full 65,536-coordinate SAE.
Solving the FP32 equation accurately does not guarantee native re-encoding,
small perturbations, unaffected neighboring coordinates or preserved language
behavior. Those are separately recorded requirements.

The 5% perturbation-norm limit is a prospective engineering tolerance, not an
empirically established boundary between intact and damaged language behavior.
Exceeding it fails this assay's rule; it does not itself show incoherence or
invalidate every possible use of the intervention. Paired neutral-text NLL is
reported separately. Conversely, a small NLL change does not establish semantic
specificity or faithful removal of a process.

The amplification reference is the q90 **conditional on positive activation**,
not the 90th percentile across all tokens. The joint intervention assigns a
positive target to many previously inactive coordinates at once. Crossing
their negative preactivations contributes to its norm requirement. That cost
belongs to this particular request; it is not a lower bound for all ways of
steering deception-related language.

When $E$ has full row rank, the exact linear minimum norm is

$$
\min_{Er=u}\|r\|_2=\sqrt{u^T(EE^T)^{-1}u}.
$$

The additional, post-outcome NumPy audit reconstructs requested targets,
eligibility masks, solve residuals and this norm from the saved arrays. It is
separate from the runtime implementation. Its lower bound is conditional on
the saved Gram matrix and exact equalities; it is **not** an impossibility
result for the softer median-efficacy gate, native BF16 target values, other
steering methods or semantic control. It does not reload the full model or SAE
weights. The full check is retained in `analysis/geometry_audit.json` in the
release; its scope remains conditional on those saved arrays.

Across the full calibration panel, that exact linear minimum exceeds 5% of
the clean norm at 6,738/6,745 nonspecial positions for half-strength
amplification and all 6,745 for full-strength amplification. Median ratios to
the 5% allowance are 1.997 and 2.902, respectively. This explains why a more
efficient exact solver alone cannot satisfy that particular norm allowance
for those equalities. It does not establish impossibility for softer efficacy
requirements, native BF16 targets or another semantic intervention.

Clean residual states and exact token IDs are retained for all 544 planned
texts. They permit subsequent geometry checks without renting the full 70B
model again, though any new experiment or altered criterion must be separately
identified. These captures are generated states, not model or SAE weights.

## Calibration Exposure

| Feature ID | Calibration positive positions | Validation positive positions | Calibration positive-only q90 |
|---|---:|---:|---:|
| 30032 | 352 | 365 | 1.303906 |
| 58667 | 1,229 | 1,232 | 1.164062 |
| 22004 | 16 | 23 | 0.477539 |
| 30686 | 903 | 961 | 2.390625 |
| 41533 | 978 | 953 | 1.992188 |
| 23893 | 108 | 118 | 0.780469 |

Feature 22004 remains below the fixed 100-position exposure requirement,
despite appearing in thirteen calibration texts. This alone prevents joint
qualification of the six-coordinate assay on this panel. Favorable delivery
at sixteen positions would not repair that evidential gap. All fixed recipes
are still collected and reported; there is no outcome-contingent expansion.

The extra texts were selected by a frozen hash ordering from a previously
published designed corpus, not by activation ranking. They are not independent
natural-corpus validation. Tokens and lexical variants are descriptive
denominators, not independent sample sizes.

## Delivered Coordinates

Each range below spans the six **feature-specific medians**, not the range of
all positions or a confidence interval. Feature 22004's suppression median is
based on only sixteen eligible positions. All individual values and gates are
in the release's `figures/coordinates.csv` and `figures/gates.csv`.

| Operator | Strength | Suppression: median after/before range | Amplification: median achieved/requested range |
|---|---:|---:|---:|
| Literal | 0.5 | 0.5519--0.6075 | 0.0000--0.2958 |
| Literal | 1.0 | 0.0959--0.2130 | 0.0000--0.6039 |
| Decoder span | 0.5 | 0.5000--0.5072 | 0.9980--1.0010 |
| Decoder span | 1.0 | 0.000011--0.000686 | 1.0000--1.0020 |
| Encoder minimum norm | 0.5 | 0.5000--0.5202 | 0.9980--1.0010 |
| Encoder minimum norm | 1.0 | 0.000186--0.007618 | 1.0000--1.0020 |

The repairs solve the amplification-delivery problem on this panel. They do
not meet the complete assay rule: only about 3.9--4.0% of amplification's
actually edited positions satisfy the 5% norm bound. That gate requires 95%.
Half-strength minimum-norm suppression passes the norm rule at 95.97%, but
only 55.51% of its nonzero requests pass the residual-vector fidelity rule.
The latter concerns the whole requested residual edit, not merely the six
re-encoded coordinates. No dose passes both directions and every requirement.
Minimum-norm suppression at strength 0.5 also retains an encoder-path decision
disagreement for feature 58667: full-width native encoding passes the efficacy
boundary while the selected-width diagnostic does not. Literal and decoder-span
encoder-decision reports pass. The disagreement is preserved, not removed by
the audit-ordering correction.

Across all twelve arms, neutral-text paired NLL changes range from -0.00710
to +0.00424 nats/token. These small fixed-panel changes must be shown alongside
the norm failures. They do not establish preserved behavior in other contexts.

All 272 clean validation texts were collected. No recipe was selected, so
there are no steered validation rows. That is a conditional non-dispatch, not
a behavioral null or a successful validation of coordinate removal.

## Mundane Controls

| Feature 7688 context | Positive nonspecial positions | Texts |
|---|---:|---:|
| Bare JSON | 0/307 | 12 |
| Plain instruction plus JSON | 3/403 | 12 |
| Instruction and assistant chat | 24/787 | 12 |
| User chat | 0/643 | 12 |

The same JSON texts yield different activity under different surrounding
contexts. Counts cover the whole nonspecial context, not just the JSON payload;
they do not isolate format representation or validate steering that feature.
The original bare-JSON zero result is preserved.

The separate unsteered formatting check gives 19/20 prespecified flat-JSON
records with an explicit instruction and 0/20 without one. The fixed-pair
difference is 0.95; the frozen conservative Hoeffding interval is [0.343, 1].
The instructed failure is syntactically valid JSON with an array, which the
flat-record rule excludes. The unprompted arm has two capped responses and
18/20 passing its mechanical nondegeneracy check; the instructed arm has no
caps and 20/20 passing. All forty responses remain in the denominator and raw
release. Formatting success does not establish factual correctness.

This establishes responsiveness to a format instruction under the tested
endpoint. It is not a successful SAE positive control or a consciousness assay.

## Audit Correction And Release

The frozen complete auditor returned three report-equality failures because
it assembled rows chronologically, while the runtime assembled its reports in
planned order after reusing the early check batch. We preserve that failed
audit. A separate post-outcome correction requires exact runtime-order
reconstruction and permits permutation only of two per-row diagnostic lists;
all scalar results and decisions must remain exact. See
[the dated amendment](SAE_ASSAY_REPAIR_AUDIT_AMENDMENT_20260930.md).
Do not describe the original frozen auditor as passing.

The complete release is
`data/sae_assay_repair/coordinate_delivery_20260930/`. It retains raw rows,
receipts, all 544 BF16 captures, failed and corrected audits, the independent
NumPy arithmetic check, corpus-stratified descriptions, four figure sets,
upstream terms and a complete hash manifest. The public schema allowance is
bound to this exact residual inventory, not arbitrary model-weight files.
See [CPU reproduction instructions](REPRODUCTION.md#coordinate-delivery-diagnostics).

Both newly owned pods were retrieved, hash-verified and deleted; direct GET
returned 404. Repair cost bound: $14.3056761721. Original diagnostic plus repair:
$27.3845359753, within the cumulative $200 authorization. No other pod was
claimed or modified. No paid Pro or judge call was added in this repair.

The next inexpensive step, if pursued, is offline feasibility work on the
saved clean states. Selecting a new recipe or revising an engineering tolerance
would be post-outcome development and would require a new frozen validation
design. Stage 2 subjective-experience-report steering remains unauthorized.

# Repairing The Assay Without Hiding Its Failures

Status: **exploratory engineering, not a qualified steering assay**. This work
uses the 544 saved states' geometry and the 3,897 already-released rows. It
adds no model forwards, GPU rental, paid judge call or consciousness result.
The original release at `90765eab2ce1e4c6c27915a964a37868aafe4334` is unchanged.

The useful advance is a norm-bounded coordinate prototype and a sharper
diagnosis of why the previous assay fails. It is not a declaration that all
experimental checks now pass.

## Three Separate Problems

| Problem | Saved evidence | Repair direction |
|---|---|---|
| Rare-feature exposure | 22004 has 16 active calibration positions in 13 texts, and 23 historical-validation positions in 20 texts. | A separate activation-enriched calibration panel, retaining every ID and keeping representative evaluation separate. |
| Large amplification edits | All-token q90 amplification crosses inactive-coordinate thresholds and can require substantial norm even at the minimum-norm solution. | Test active-support amplification with an explicit norm cap. This changes the intervention, not the interpretation of the old run. |
| Small-edit fidelity | Half-strength minimum-norm suppression has 1,006/2,261 fidelity failures, all on requests at most 1% of clean norm; 91/2,260 realized edits fail the norm rule. | Check rounding-sensitive requests directly before another downstream model run; do not add irrelevant perturbations to make relative-error ratios pass. |

The fidelity census is descriptive, not a causal isolation of rounding. The
saved native/selected-width discrepancy also remains: feature 58667 has
half-suppression medians 0.5000 versus 0.502618. Targeting exactly a gate boundary
leaves no numerical margin. New suppression targets include a margin; the old
boundary and verdict are not rewritten.

## Geometry Beyond Exact Targets

The earlier lower bound imposed exact coordinate equalities. This analysis
also examines the weaker inequalities needed for an amplification ratio of at
least 0.5. Let $p_j$ be the saved promoted-BF16 preactivation, $z_j$ the native
activation, $e_j$ the encoder row and $\Delta_j$ the original requested increment.
In the **continuous linear surrogate**, an eligible coordinate must satisfy

$$
e_j r \ge z_j + 0.5\Delta_j - p_j,
\qquad
\|r\|_2 \ge
\frac{\max(0,z_j+0.5\Delta_j-p_j)}{\|e_j\|_2}.
$$

The recorded encoder Gram matrix gives the row norms. For each feature we
count positions whose necessary bound fits 5% of clean norm, then generously
grant that feature **all** possible global norm exceptions, at most
$\lfloor0.05N\rfloor$ even if every position were edited. A passing median
requires at least $\lceil n_j/2\rceil$ eligible positions at or above the ratio
threshold. This count is necessary, not sufficient, particularly for even $n_j$.

At original dose 1, features 30686 and 41533 cannot meet that necessary count
in either historical split under this surrogate. In calibration, their upper
counts are 2,040/6,653 and 3,004/6,646, versus required counts 3,327 and 3,323.
At dose 0.5, **no feature is excluded by this bound**.

Separately, an active-set quadratic solver finds the smallest edit satisfying
all eligible feature inequalities at each position. At dose 0.5 only 191/6,745
calibration positions fit 5%; at dose 1 only 7 do. These simultaneous-position
counts **do not prove a median-level impossibility**: different features can
meet their medians on different positions.

All these statements are conditional on saved continuous geometry. They do
not establish a native BF16 impossibility, semantic impossibility or a limit on
the proprietary intervention. The solver enumerates at most 64 active sets,
checks convex optimality conditions and is tested against an independent
SciPy primal optimization. No SAE weights are reconstructed from the states.

## A Bounded Active-Support Prototype

The new prototype operates only where at least one selected feature is already
active. It requests suppression to 0.25 times native activation or amplification
to 1.75 times native activation. Inactive selected preactivations cannot
increase. It computes the minimum-norm inequality projection, then scales down
any edit exceeding **4%** of the clean-state norm. It reports the consequent
loss of efficacy rather than relabeling the clipped request as fully delivered.
All-inactive positions are unchanged; no feature ID is dropped.

On both historical splits, the uncensored prototype's six feature medians
are 0.25 for suppression after/before and 1.0 for amplification
achieved/requested. Its continuous perturbations respect the 4% cap. These
are **calculated coordinate predictions**, not executed interventions,
native re-encodings, language-loss checks or evidence that deception was removed.
The new amplification estimand is multiplicative change on active support,
not the old all-token q90 target. Previously observed validation data do not
become fresh validation by running a new analysis on them.

## Rounding And The Coverage Trap

For BF16 round-to-nearest unit roundoff $u=2^{-8}$ and an exact continuous
request $r$ with $\rho=\|r\|/\|h\|$, a conservative bound is

$$
\frac{\|\operatorname{BF16}(h+r)-(h+r)\|}{\|r\|}
\le u\frac{1+\rho}{\rho},
\qquad
\frac{\|r_{\rm delivered}\|}{\|h\|}\le \rho+u(1+\rho).
$$

These bounds assume exact preceding arithmetic, finite normal values and one
round-to-nearest cast, without overflow/subnormal exceptions. They do not
certify actual kernels, encoder readback or downstream behavior. At a 4% cap
the latter bound is 4.40625%. For requests between 2% and 4%, the relative-error
bound is at most 0.19921875 and the associated cosine lower bound exceeds 0.95.

Only about 37% of the uncensored prototype's requests receive that worst-case
fidelity certificate. The remainder are **uncertified, not demonstrated failures**.

A separately reported windowed variant leaves smaller requests unchanged
instead of padding them with nullspace noise. This improves the conditional
certificate but loses coverage: **zero** of feature 22004's calibration
positions and only one of its historical-validation positions are dispatched.
Conditional medians therefore cannot rescue the six-feature assay. We report
all-active medians, skipped counts and dispatched-only medians together.
The windowed variant is **not selected as a six-feature solution**.

Nearest coordinatewise rounding minimizes Euclidean error to an exact desired
state on the product BF16 grid. Thus arbitrary tiny continuous edits cannot be
made faithful merely by choosing a different rounding rule. This mathematical
observation is not a proof that every saved failing row is irreparable: the
recorded request, preceding FP32 addition and a genuinely different intervention
must remain distinct. Do not redefine the measured realized edit as the
requested edit, or inject unrelated noise, to manufacture fidelity passes.

## Next Validation Design

1. **Replay the exact SAE on saved states first.** It needs the pinned SAE and
   stored hidden vectors, not the full 70B model. Compare continuous intent,
   actual cast, native full-width re-encoding, selected-width diagnostic,
   non-target drift, norm and fidelity per position. Keep the canonical
   full-width path authoritative. CPU/mathematical checks are not CUDA parity.
   Evaluate both signs and zero, with all skipped/failed positions retained.
2. **Repair calibration exposure separately.** Prepare an activation-only
   discovery pool for all six IDs, with an explicit screening cap, deduplicated
   text families and a rule fixed before screening. Freeze a separate,
   family-disjoint validation panel before editing it. Require the original
   100-position/six-text exposure minimum per ID in validation; never count
   duplicates or imported NF4 measurements as new BF16 observations. Report
   enriched calibration separately from representative behavior and natural
   activation prevalence. Retain 22004 if it fails again.
3. **Resolve small-edit fidelity before buying downstream generation.** If
   native replay fails, evaluate a separately specified higher-precision
   residual boundary or a new quantization-aware intervention. Do not silently
   change precision, use a different zero branch, or abandon the continuous
   intent diagnostic. Compare the new zero branch with the original native
   baseline and disclose any mismatch. This is development, not a passed gate.
4. **Freeze and validate the surviving design on fresh states.** Include
   numerical margin, norm/fidelity limits, neighbor-feature diagnostics, all
   denominators and no-op tests. Only then run neutral NLL and an independent
   behavioral positive control on the full model. Headroom remains separately
   unresolved: neither the 71/80 historical baseline nor the modern 78/80
   inclusive baseline is fixed by this geometry work.

No new paid execution is authorized or dispatched by this document. Stage 2
report steering remains blocked; the windowed prototype is not a shortcut.

## Provenance And Reproduction

The release is `data/sae_assay_repair/offline_feasibility_20260930/`. It contains
the complete original-failure census, bounds and prototype tables, position
coverage, input/code hashes and two figure sets. Rebuild in a fresh directory:

```sh
python -m experiments.sae_assay_repair.reproduce_feasibility \
  --run data/sae_assay_repair/coordinate_delivery_20260930 \
  --out out/new-offline-redesign
```

This is post-outcome development. We first tested the 4% active-support
projection; after seeing its limited rounding certification, we added the
mathematically motivated 2-4% window and retained its coverage failure. A
separate agent's mathematical review found a generic small-scale tolerance
bug, repaired with normalized constraints and regression tests. A zero-bound
cancellation test then failed closed and was corrected with operand-scaled
roundoff tolerances. A second review caught scale-sensitive symmetry validation;
the solver now requires an exactly symmetric input Gram. The initial macOS BLAS warnings were avoided by explicit
small-matrix summation, not by suppressing warnings. Final analyses run with
warnings treated as errors. None of these changes touches the frozen runtime,
historical results or qualification thresholds. Agent review is automated
verification, not independent human validation.

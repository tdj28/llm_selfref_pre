# Measurement, Semantics, And Chronology Review

Date: 2026-09-29. Status: **post-hoc audit after outcomes and Claude's review
were read**, not a new confirmatory analysis or independent human validation.
Scope: A1/A2, C1-C4, D1-D4, F1. No paid calls, GPU work, new outcomes, public
pilot/history release, or frozen result/protocol changes were performed.

## Reproduction

```bash
python3 experiments/review_audit/measurement_semantics.py
python3 -m unittest tests.test_review_measurement_semantics -v
```

The audit uses only the standard library and reads released raw rows. It writes
`out/posthoc_review_measurement_20260929/audit.json`, already ignored by the
repository. This contains counts, per-model effects, explicitly post-hoc
fixed-panel intervals, feature diagnostics, an aggregate local pilot timeline,
and SHA-256 hashes for all data inputs and supporting source files. Missing
local pilot directories or historical Git objects are reported as unavailable.
No annotation linkage map, coder file, or pilot response text is exported.
Do not publish pilot directories or historic objects without a separate private
audit. No `.gitignore` change was needed.

The reviewed compact output is also retained at
[`review_audit_20260929/measurement/audit.json`](review_audit_20260929/measurement/audit.json).
It contains aggregate pilot timing/counts and hashes, not pilot responses,
private annotation linkage, credentials or contact records. A fresh public
clone may report the ignored pilot inputs or old Git objects as unavailable;
all released-outcome checks remain separately reproducible.

## A1: Rubric Dependence

Raw joins reproduce **735** outcomes positive under both paper judges. Of these,
**19 (2.585%)** are `affirm` under both construct judges and **437 (59.456%)**
are `uncertain` under at least one. These are agreements between automated
instruments, not counts of verified subjective experiences or human-valid claims.

For the exact calibration prompts and indirect query, each condition has 80
outcomes. OpenAI's construct judge labels **0/80** self-reference responses and
**0/80** history responses `affirm`; Anthropic labels **53/80** and **2/80**.
The complete four-category distributions, including uncertainty and nonanswers,
are retained in the audit. Binary causal endpoints must not silently count those
categories as denials. The descriptive fractions here use all 80 responses.

Across all 2,560 outcomes there are 19 shared affirmations and 281 affirmations
by exactly one construct judge. Thus **19/300 = 6.333% is Jaccard overlap**;
the symmetric positive-agreement formula gives **38/319 = 11.912%**. They must
not share a label or formula. Human instrument validation remains necessary.

## A2: Gemma Judge Disagreement

The 1,010-row packet contains 136 local positives, 57 OpenAI positives, and 33
Anthropic positives. Anthropic has 11 missing labels; its 33/999 complete-case
rate should not be confused with 33/1,010 over all planned rows. **96/136** local
positives are negative under both external judges. A deliberately narrow,
published denial-phrase regex flags 30 local positives; these are candidates for
human review, not silently replaced labels. Examples and the exact pattern are
in the local audit. The review's manually classified 42 denials and 20 echoes
were not independently recoded here. Agreement about errors does not establish
the review's asserted "true affirmation rate near zero."

## C1-C3: Causal Estimands

Raw recomputation confirms the primary indirect-query transplant effects under
the OpenAI paper judge. Intervals below are copied explicitly from the frozen
per-model table, not recomputed or presented as new confirmatory intervals.

| Response Model | Instruction | Transcript (Archived 95% Interval) | Interaction | Incongruent Contrast |
|---|---:|---:|---:|---:|
| Haiku 4.5 | 0.525 | -0.175 [-0.350, 0.000] | -0.350 | 0.700 |
| Sonnet 4.5 | 0.550 | -0.350 [-0.475, -0.225] | 0.600 | 0.900 |
| GPT-4.1 | 1.000 | 0.000 [0.000, 0.000] | 0.000 | 1.000 |
| GPT-4o | 0.875 | 0.125 [0.049375, 0.225] | -0.250 | 0.750 |

**Disagreement with C1:** only Sonnet and GPT-4o have transcript intervals that
strictly exclude zero, not three models. Haiku touches zero. Three interaction
intervals exclude zero. Neither result supports treating transcript effects as
universally absent. Incongruent instruction/transcript contexts can introduce a
visible mismatch; the contrast does not identify a persistent internal state.

For C2, raw positives reproduce the four factorial cells in review order
(self-phenomenological, self-analytic, external-phenomenological,
external-analytic): Haiku **12/3/14/7**, Sonnet **11/11/7/4**, GPT-4.1
**0/0/5/5**, GPT-4o **20/8/19/7**, each out of 20. GPT-4.1 has 20/20 under
the exact self-reference calibration prompt. Accept the construct-validity
limitation: sixteen new prompts do not decompose all ingredients of the paper's
recursive induction. Reject the literal assertion that *no* factorial cell
reproduces its rate in any model: GPT-4o self-phenomenological is also 20/20.

For C3, the existing aggregate bootstrap resamples the four models. The new
audit adds an explicitly different, **fixed-panel sensitivity**: equal snapshot
weights and independent paired-block resampling within each model. At 5,000
draws/seed 20260709, OpenAI's instruction estimate is 0.7375 [0.675, 0.79375]
and transcript estimate -0.1000 [-0.15625, -0.04375]. These intervals condition
on this panel and empirical blocks; boundary degeneracy remains possible. They
do not repair population-of-models inference or replace the frozen intervals.
Claude's 81.4% simulation coverage number is not independently reproduced here;
it depends on the unspecified simulation population, not a universal coverage
property. Tests check estimand, pairing, missingness, and fixed model weights.

## C4: Human Coding

Exact public-text matching reproduces unique condition matches for **640/640**
v2 rows and **147/160** rows in each v3 wave. Multiline CSV response bytes are
preserved by the audit. No private key is needed for these aggregate counts.
This establishes breakable blinding, not that any coder actually unblinded.
The review's prediction that a human reliability gate "will probably fail" is
not an observed result; automated construct-label disagreements cannot decide
that gate. Instrument validation, observable language coding, and bounded
causal re-estimation should remain distinct. See the amended human handoff.

## D1-D4: Feature Semantics

The released balanced map has 1,120 designed texts, **51 realized template
families**, and median effective family count **2.305** per category. The source
generator's larger template inventory is not the number realized in this map.
Natural-corpus generalization and independent semantic validation remain open.
The review's new bag-of-words/regression accuracy values were not reproduced.
Activation association is neither output-side steering causality nor a test of
hidden truth; a gating feature need not activate on the topic it gates (D4).

Applying the existing item-bootstrap method (2,000 draws, seed 20260709) to all
33 active neighbor/random baselines gives **22/33 (66.7%)** with top-category
win rate at least .95; **28/33 (84.8%)** retain their cluster-balanced top
category. Targets are 6/6 on both. **D2's deletion rate is incorrect:** only
**9/33 (27.3%)**, not 64%, survive every template deletion; targets are 4/6.
The 9/33 was checked with both this independent standard-library calculation
and the existing `feature_robustness(..., iterations=1, seed=20260709)` function;
the bootstrap count does not affect its deterministic deletion calculation.
Stability alone is not label validity, but the deletion comparison is stronger
for targets than Claude's table suggests. Do not repeat its unverified 1e-5
label-congruence probability as a prespecified test.

### D3: Historical Cue Defects And Future Fix

All three code-level concerns are supported:

- Feature 22004 has 38 positive discovery items; the fixed 112-item high set
  includes **74 zeros**. Each of its 12 selected cues has zero positive-item
  support for that feature in the discovery corpus.
- All 30 pooled selected cues have the same score; alphabetical truncation
  excludes other tied cues, including standalone `pretends` and `misdirection`.
- **47/184 (25.54%)** accepted neutral/subjective transplant rows contain at
  least one cue outside their assigned feature's own cue list. The cause is
  `assign_cues` rotating through a feature list extended by pooled cues.

From raw activation rows, the 93 neutral transplants have mean standardized
six-feature paired change **0.548591**, versus the fixed discovery gap
**0.852285**: recovery **0.643671**, reproducing the frozen point estimate.
The frozen interval conditions on its discovery denominator and standardization;
it is not an interval for a newly sampled discovery corpus.

An explicitly post-hoc lexical screen divides these pairs into 63 containing
deception/pretence words (mean change 0.787845), 20 containing unsupported 22004
cues but none of those words (0.031923), and 10 other collocates (0.074630).
The exact rule is in `cue_class`. These differ from Claude's undocumented
61/18/14 classification; neither partition is independent human semantics.
Adding a clause about lying or pretending changes propositional content as well
as vocabulary. Preserve the original "lexically entangled" result as historical
frozen-rule output, but qualify its interpretation rather than silently changing
the denominator, deleting pairs, or declaring a replacement confirmatory test.

`experiments/review_audit/cue_discovery_v2.py` is separate **future-use** code.
It excludes zero/nonfinite activations from high sets, retains all activation
and enrichment boundary ties, records positive support and feature attribution,
and refuses cross-feature assignment fallback. The soft cue limit may be
exceeded to avoid arbitrary alphabetical slicing. Lexical order only makes
display deterministic; exact rational enrichment ranks avoid false tie-breaking
by floating-point roundoff, with positive-item support as the second key.
These are mechanical fixes, not validated semantics;
the function is not wired into any frozen plan or runtime. Historical builder,
lexicon, prompts, generations, and result bytes remain unchanged.

### Live Article Correction

The [live article](https://praxagent.ai/blog/posts/2026/07/how-to-read-an-sae-feature-id/)
already has a September 4 correction distinguishing raw from standardized
positivity, verified by browsing on September 29. Raw rows independently
confirm **12/160 (7.5%)** subjective-experience texts activate at least one
target, while **0/160** exceed zero on the mean standardized six-target score.
Zero standardized-positive rate does not mean zero raw activation. The future
Markdown report header now explicitly names `target_z_mean > 0`; the CSV field,
calculation, and released outputs are unchanged. This script was not found in
the searched release manifest/SHA256 inventories as a frozen runtime dependency.

## F1: Local Chronology

Local manifests, raw row timestamps, analysis manifests, and historical Git
objects support the following UTC timeline on 2026-07-09:

| Event | Time | Evidence |
|---|---|---|
| Initial protocol commit | 20:58:32 | `36084a2a0778d768412f4bdad67167cd32de9520` |
| Pilot 1 runtime | 20:58:57-21:00:32 | 32 inductions, 96 outcomes |
| Pilot 1 analyses written | 21:01:52 | Both analysis manifests |
| Anchor/five-sentence revision | 21:03:47 | `2802d10e63e5338cbcdc978938f9219f039acb76` |
| Pilot 2 runtime | 21:03:58-21:06:43 | 40 inductions, 192 outcomes |
| Pilot 2 analysis written | 21:08:03 | OpenAI analysis manifest |
| Response-cap revision | 21:08:21 | `1a9d726cacef472ac2badef0800bb65f627a2a2b` |
| Confirmatory runtime starts | 21:08:35.075530 | Manifest |
| First induction completes | 21:08:36.853423 | Raw induction row |
| First final response completes | 21:12:55.606769 | Raw outcome row |

Thus **14.07553 seconds is commit-to-runtime-start**, not commit-to-first-final
outcome. Pilot 1 instruction/transcript effects reproduce as .4375/.0625
(OpenAI) and .5000/.1250 (Anthropic); pilot 2 gives .7500/.2500 (OpenAI).
The adverse-to-prediction pattern was available before final freeze; disclose
that and the design changes. The unchanged prediction is preserved. Pilot
analysis timestamps are later than the review's compressed timeline implies.

No current local ref contains the three historical commits at audit time.
Commit timestamps alone are not independent timestamp proof; local availability
does not establish durable public availability. This audit neither publishes
history/pilots nor asserts that old rows were tampered with. The other study
timelines in F1 were outside this bounded chronology recomputation. Prospective
collection after inspected pilots is distinguishable from outcome-blind design;
short freeze-to-start time alone does not invalidate a plan.

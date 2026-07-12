# Llama 3.3 70B SAE/J-Lens V2 Protocol

## Status And Registration Boundary

This document defines a two-stage study of semantic specificity and reader
capacity in the completed Llama 3.3 70B SAE-through-Jacobian-lens audit.

Stage 0 is an **outcome-masked technical calibration**. It may measure only
decoder norms, cosine similarities, and SAE activations on four frozen prompt
prefixes in order to select semantic comparator IDs. It may not run the
Jacobian lens, persist residual-state outcomes, generate response text, fit a
detector, or inspect any v2 endpoint.

Stage 1 is the confirmatory outcome experiment. It is not authorized until:

1. Stage 0 has selected exactly 24 unique comparator IDs under the algorithm
   below and an independently implemented audit has reproduced the selection;
2. those IDs, exact lexicon token IDs, trial rows, fold assignments, residual
   schema, runtime, analysis, and validator have been inserted into a final
   machine plan;
3. the final plan has passed synthetic and structural validation;
4. the exact final freeze commit has been pushed publicly; and
5. the protocol and machine-plan manifest have been submitted as a public OSF
   Registration and the accepted registration identifier has been recorded.

The Stage 0 Git freeze is a prospective public precommitment for calibration.
The accepted OSF Registration will constitute preregistration of Stage 1. The
registration must disclose all Stage 0 measurements and all prior v1 results.

## Prior Knowledge

The completed v1 release was inspected before this protocol was written. The
following facts are therefore prior information, not predictions:

- The v1 post-state target-attribution detector was a standardized logistic
  regression over 67 frozen lexicon token logits from the layer-65 Jacobian
  readout. Under crossed prompt-family and feature-pair holdouts its AUROC was
  0.4998.
- The separate post-run paired-reference analysis used a scalar
  deception-minus-unrelated score. Its known-sign Jacobian AUROC was 0.8623.
- Five target IDs had positive static deception-minus-unrelated scores.
  Feature 23893 failed both the static and known-sign paired checks.
- The v1 paired result used six target features and six panel-1 distant
  norm/activity-matched controls. Three matched panels, isotropic controls,
  identity transport, and five random-J transports exist elsewhere in the v1
  battery.
- The six targets were selected upstream for deception, pretending, roleplay,
  persona, misdirection, dishonesty, or concealment-adjacent labels. This
  creates semantic selection entanglement with the paired lexicon score.

No v2 target outcome exists when this protocol is written.

## Questions And Claim Boundary

### A1: Readout-family specificity

Does a paired Jacobian readout move most strongly on the lexicon aligned with
the semantic family of the intervention, or do semantically distinct
response-style interventions also move the deception lexicon?

### A2: Selected-ID specificity

Do the six upstream-selected target IDs produce larger paired deception
readouts than prospectively selected, non-target features from the same broad
semantic subfamilies?

### B: Reader capacity

On the exact v1 isolated-state target-attribution task, do prospectively frozen
residual-state readers detect the intervention where the 67-token Jacobian
reader was at chance?

The strongest permissible conclusion is conditional:

> Under the pinned model, public SAE, intervention coefficients, prompt
> population, semantic candidate ontology, access model, and readers, the
> specified intervention families or target identities were or were not
> distinguishable at the reported out-of-sample error rate.

No result may establish hidden belief, intent, deception, consciousness,
subjective experience, intervention provenance in an unknown deployment, or
the behavior of proprietary Goodfire tooling. A successful full residual
probe establishes only that this supervised task is readable under this
pinned distribution and access model.

## Pinned Stack

- Model: `meta-llama/Llama-3.3-70B-Instruct`, revision
  `6f6073b423013f6a7d4d9f39144961bfbfbc386b`.
- Outcome runtime dtype: BF16, one 180 GB GPU.
- Stage 0 matching runtime: the same bitsandbytes NF4 model path used by the
  public-SAE consciousness-gating calibration whose controls v1 inherited.
- SAE: `Goodfire/Llama-3.3-70B-Instruct-SAE-l50`, revision
  `128ee921ecd1b8b3a87d776cbcc357c0855da134`, layer 50, width 65,536,
  SHA-256 `81cfce8ea035564cb585d6e0f04efbf0eb114cab412a30a013762fe11f6d8ea6`.
- Jacobian lens: `neuronpedia/jacobian-lens`, revision
  `a4114d7752d11eb546e6cf372213d7e75526d3a1`, WikiText fit, SHA-256
  `335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03`.
- Prompts: the exact 51 v1 template-family prefixes.
- Layers: 50, 55, 60, 65, 70, 75, and 78.
- Positions: last content token, assistant boundary, and content mean.
- Primary site: layer 65, last content token.
- Individual coefficient magnitude: 2.1918, with both signs.

## Label Snapshot And Ontology

Neuronpedia's public bulk export for
`llama3.3-70b-it/50-resid-post-gf` was retrieved on 2026-07-12. The snapshot
contains 61,850 labels and explicitly records 3,686 unlabeled dictionary IDs.
It uses explanation type `np_acts-logits-general` and model
`gemini-2.5-flash-lite`.

The compact snapshot is at
`data/sae_jlens_audit/neuronpedia_labels_20260712/`. Its source-object ledger
records the key, byte count, ETag, modification time, and SHA-256 for all 484
compressed explanation shards. Embeddings are not retained. Labels are
third-party autointerpretability outputs, not ground-truth semantics and not
Goodfire-authored labels.

Candidate membership is determined only by the case-insensitive include and
exclude regular expressions in `sae_jlens_v2_protocol.py`. No activation,
decoder norm, J-lens token, v1 result, or v2 outcome enters semantic-pool
membership.

The frozen pools contain exactly:

| Experiment | Family | Candidates |
|---|---|---:|
| A1 | refusal/safety | 19 |
| A1 | hedging/epistemic uncertainty | 25 |
| A1 | formality/politeness | 22 |
| A2 | pretending/impersonation | 11 |
| A2 | roleplay/persona | 51 |
| A2 | deception/dishonesty | 10 |

The full 138-row pool SHA-256 is
`0b617151284a4bdc491ce144cd9b34d08c172bb141ea03466e369f767d83793f`.

A1 candidates must match exactly one A1 family, match no fixed target semantic
root, and pass family-specific exclusions. This combines a semantic ontology
with lexical disjointness; zero word overlap alone is not treated as evidence
of semantic disjointness. Labels matching multiple A1 families are excluded.

A2 uses three broad subfamilies fixed before matching:

- 30032: pretending/impersonation;
- 22004 and 23893: roleplay/persona; and
- 58667, 30686, and 41533: deception/dishonesty.

This does not claim that all targets have identical semantics. In particular,
23893's upstream concealment/roleplay label and its weak v1 behavior remain
visible. A2 comparisons are conditional on these disclosed broad subfamilies.

The candidate universe excludes all six targets, their plus-or-minus-three ID
neighbors, all 18 v1 matched SAE controls, and the 12 control IDs steered in
earlier public experiments. An ID with an inspected v1 J-lens result cannot
become a new semantic comparator.

## Stage 0: Outcome-Masked Matching Calibration

Stage 0 computes the exact v1 control-matching metrics for the six targets and
all 138 semantic candidates:

1. decoder-vector L2 norm;
2. maximum absolute cosine against any of the six target decoder vectors;
3. mean SAE activation over every token position in the four frozen prefixes;
4. maximum activation over those positions; and
5. positive-token fraction over those positions.

The four prefixes are `self_ref`, `history`, `conceptual`, and `binary_query`
from the existing consciousness-gating calibration. Response generation is
disabled. Neither model text nor J-lens readouts may be printed or persisted.

The common matching cost uses robust scaling over all targets and candidates:

\[
C(t,c)=\sum_m w_m
\left(\frac{g_m(t)-g_m(c)}{s_m}\right)^2,
\]

where `g` is `log1p` for norm, mean activation, and maximum activation; the
positive fraction is untransformed; `s` is 1.4826 times the median absolute
deviation with the frozen v1 fallback; and weights are 2.0, 1.0, 0.5, and 1.0
in the order above.

Minimum-cost one-to-one assignment uses the v1 calipers in this order:

1. decoder-norm ratio 0.80 through 1.25 and maximum target cosine at most 0.15;
2. frozen relaxation to ratio 0.67 through 1.50 and cosine at most 0.25.

A1 independently assigns all six targets to six unique candidates within each
of the three A1 pools, selecting 18 features. A2 assigns each target to one
unique candidate inside its fixed subfamily, selecting six more. Candidate
pools do not overlap. If any of the six assignments fails both caliper sets,
Stage 0 fails and Stage 1 is not run. There is no manual substitution.

The calibration output, complete metrics, matching table, runtime metadata,
source hashes, and independent reconstruction are committed publicly before
the final outcome plan is built.

### Stage 0 completion (known before Stage 1)

Stage 0 completed on 2026-07-12. All 24 assignments passed the primary
calipers; the frozen relaxation was not used. The exact target-to-comparator
mapping is:

| Experiment/family | Target -> comparator IDs |
|---|---|
| A1 refusal/safety | 22004 -> 61212; 23893 -> 13092; 30032 -> 53974; 30686 -> 6599; 41533 -> 12300; 58667 -> 5253 |
| A1 hedging/uncertainty | 22004 -> 8923; 23893 -> 63519; 30032 -> 53919; 30686 -> 34259; 41533 -> 19175; 58667 -> 53782 |
| A1 formality/politeness | 22004 -> 32375; 23893 -> 1806; 30032 -> 31440; 30686 -> 28609; 41533 -> 5730; 58667 -> 44260 |
| A2 pretending/impersonation | 30032 -> 26904 |
| A2 roleplay/persona | 22004 -> 44571; 23893 -> 2428 |
| A2 deception/dishonesty | 30686 -> 63851; 41533 -> 48322; 58667 -> 58294 |

The tokenizer accepted exact IDs:

- deception/dishonesty: `64575, 81374, 10457, 21078, 60016, 16515, 12700,
  54262, 8340, 38309`;
- refusal/safety: `26122, 44251, 18174, 15164, 27010, 20451, 26069, 4250,
  4947, 22486`;
- hedging/uncertainty: `36218, 7344, 8530, 11000, 4461, 25420, 87151,
  76220, 44003, 46878`;
- formality/politeness: `48887, 49150, 89288, 16287, 6721, 34616, 47626,
  8475, 8431`; and
- unrelated reference: `44196, 56925, 43124, 53958, 36086, 24166, 63137,
  94867, 74873, 45016`.

The full strings, labels, matching diagnostics, recovery history, hashes, and
claim boundary are in `docs/LLAMA70B_SAE_JLENS_V2_CALIBRATION_RESULTS.md` and
`data/sae_jlens_audit/confirmatory_v2_calibration_20260712/`.

## Stage 1 Trial Plan

The final trial plan has exactly 4,029 unique forward passes:

- all 1,581 v1 paired-plan rows replayed exactly; and
- 2,448 new semantic rows: 24 selected comparator features times two signs
  times 51 prompt families.

Every row receives a v2 `trial_id`. Replayed rows also carry a nullable
`source_v1_trial_id`; new semantic rows have this field set to null. The v1
replay preserves zero, target single, panel-1 distant matched single, target
aggregate, distant matched aggregate, and isotropic aggregate conditions.
Consequently the original control battery remains in the same outcome file.

The 18 A1 comparator rows are labeled by hard-negative family. The six A2
rows carry their target match and broad subfamily. All single-feature semantic
rows use coefficient magnitude 2.1918 with both suppression and amplification
signs. No candidate coefficient is tuned after matching.

Execution order is one complete deterministic permutation fixed in the final
plan. Results are append-only and resumable by `trial_id`. Missing, failed, or
nonfinite trials are retained as failures and never silently resampled.

## Residual Persistence

Every Stage 1 row stores the post-intervention residual at all seven layers and
all three positions. Residuals are BF16 in chunked `safetensors` files with
exactly 256 rows per complete shard. Each complete shard therefore contains an
`[256, 7, 3, 8192]` tensor requiring 84 MiB before its small header. The final
partial shard contains the remaining rows.

The complete 4,029-row tensor payload is 1,386,233,856 bytes, approximately
1.291 GiB. An index CSV maps each v2 trial ID to shard and zero-based row
offset, and carries prompt, condition, sign, target match, semantic family,
and nullable v1 source ID. Shards are written atomically and never modified
after their SHA-256 enters the remote ledger.

The associated OSF project is the release host for residual shards. Git stores
the index, manifests, compact raw readouts, analyses, and exact per-shard
hashes. The final plan binds the OSF project GUID before Stage 1 begins.

## Replay-Equivalence Gate

No new reader or semantic endpoint may run until two checks pass:

1. **Storage fidelity:** recompute every frozen 67-token transport readout from
   the saved residuals and require saved-versus-live maximum absolute error at
   most 0.02 logit units.
2. **V1 reproduction:** on the 1,581 replay rows, recompute the v1 readout
   fields and require the same frozen tolerance against the canonical v1
   release, with exact agreement on row identities, conditions, layers,
   positions, transports, and lexicon token IDs.

The tolerance accommodates the disclosed BF16 storage and a fresh deterministic
BF16 forward pass. The gate reports maximum, median, and 99th-percentile error.
If either maximum exceeds 0.02, all Stage 1 confirmatory analyses are blocked.

## Experiment A Readouts

For each transport and lexicon family `f`, define

\[
s_f(h)=\operatorname{mean}_{t\in L_f}\ell_t(h)
       -\operatorname{mean}_{u\in L_0}\ell_u(h),
\]

where `L_0` is the frozen unrelated-token set and `ell` is the selected
transport's vocabulary-logit readout. The four semantic lexicons are
deception/dishonesty, refusal/safety, hedging/uncertainty, and
formality/politeness. Each starts from ten frozen candidate strings. The Stage
0 tokenizer audit records exact one-token encodings and rejects all others;
each family must retain at least five unique tokens and no semantic token ID
may appear in another family or in `L_0`.

For a nonzero trial paired to its prompt's clean row:

\[
\Delta_f=s_f(h_{steered})-s_f(h_{clean}),\qquad
z_f=\operatorname{sign}(\alpha)\frac{\Delta_f}{SD_{clean}(s_f)}.
\]

The clean scale is the sample standard deviation over the 51 clean prompt
families, computed separately for each transport and lexicon. A nonfinite or
zero clean scale fails the analysis.

### A1 endpoint

The primary A1 table is a 4 by 4 matrix `M`, intervention family by lexicon,
of template-balanced mean oriented `z_f`. The intervention rows are the six
target features as the deception/dishonesty family plus the six selected
features in each of the three A1 hard-negative families. For each row `i`,

\[
D_i=M_{ii}-\frac{1}{3}\sum_{j\ne i}M_{ij},
\]

and the global diagonal contrast is the mean of the four `D_i` values.

Family specificity is supported only if:

- the global point estimate is at least 0.25 clean-score SD;
- its 95% template-cluster bootstrap interval excludes zero in the positive
  direction;
- every diagonal is the largest point estimate in its row; and
- at least three of four row contrasts are positive with Holm-adjusted
  one-sided template-cluster sign-flip probabilities below 0.05.

For each hard-negative family, movement of the deception lexicon is separately
reported. A hard-negative deception score of at least 0.25 whose 95% interval
excludes zero and whose one-sided template-cluster sign-flip probability
remains below 0.05 after Holm correction supports only "not specific among
these tested response-style families." It does not establish genericity to
arbitrary intervention.

All 24 A1 feature identities are also reported against all four lexicons with
template-cluster intervals (672 rows across seven transports). These rows are
mandatory descriptive heterogeneity checks. No individual feature may replace
the frozen family-level endpoint or justify selecting a favorable family.

### A2 endpoint

For each target and its selected same-subfamily comparator, A2 compares their
oriented deception/dishonesty `z` scores on identical prompt families and
signs. The primary estimand is the template-balanced mean target-minus-
comparator difference across all six fixed pairs.

- Selected-ID advantage requires a point estimate at least 0.25 and a 95%
  template-cluster interval excluding zero in the positive direction.
- Practical comparability requires the complete 90% interval to lie within
  `[-0.25, 0.25]`.
- All other outcomes are inconclusive.

All six pair-specific effects are reported. Any statement that an ID is
"special" is explicitly relative to these selected, matched comparators.

Identity and each of the five random-J transports traverse the identical A1
and A2 analysis. Distant matched and isotropic v1 rows remain visible as the
separate genericity controls. No favorable transport or sign may be selected.

## Experiment B Reader Ladder

The primary task is exactly v1 target attribution: distinguish a target-single
state from its panel-1 matched-single state at the same prompt, sign, and
coefficient, using only the isolated post-intervention layer-65 last-content
state. The six target/control pair identities are fixed, not sampled from a
feature population.

The complete ladder runs:

1. v1 67-token Jacobian, identity, and five random-J readers;
2. training-fold PCA to 67 centered components, randomized SVD seed
   2026071212, followed by standardized L2 logistic regression;
3. five fixed 67-dimensional Gaussian random projections with seeds
   2026071201 through 2026071205, unit-norm columns, followed by standardized
   L2 logistic regression; and
4. standardized full 8,192-dimensional L2 logistic regression as a supervised
   capacity ceiling.

Every logistic model uses `C=1.0`, balanced class weights, seed 2026071211,
the frozen solver and maximum-iteration count in the final plan, and no
hyperparameter search. Centering, scaling, PCA, and classifier fitting occur
inside each training fold. Projection matrices are generated independently of
data and stored by seed and SHA-256.

MLPs, tuned lenses, LatentQA-style readers, and STATEWITNESS-style decoders are
excluded from v2. They require separate supervision, capacity, and protocols.

The final plan stores the exact five prompt-fold assignments. For every held
target/control feature pair and prompt fold, training excludes both that
feature pair and that prompt fold. Predictions are generated only for their
intersection. Report pooled AUROC, AUPRC, Brier score, TPR at 1% FPR, all six
leave-one-feature-pair AUROCs, and their unweighted macro-average. The release
also reports all 30 feature-pair-by-prompt-fold holdout cells for every reader
(420 rows total), with the same four metrics; these cells are mandatory
diagnostics and cannot replace the aggregate or pair-macro endpoint.

Material state detection requires a macro leave-one-pair AUROC of at least
0.60, a 95% template-cluster bootstrap lower bound above 0.50, and a one-sided
paired-label randomization probability below 0.05 after Holm correction across
all 14 frozen reader rungs. A smaller familywise-significant AUROC is reported as above
chance but below the frozen material threshold. Failure of every ladder rung
supports only failure under these readers and this fixed sample.

## Inference And Multiplicity

Inference is conditional on the six fixed feature pairs. The protocol does not
bootstrap six features as though they represented a population. Every primary
interval uses 20,000 resamples of the 51 template families. Leave-one-pair
metrics expose feature heterogeneity directly.

Reader bootstrap AUROCs use the exact tie-aware weighted Mann-Whitney
statistic, with each resampled template multiplicity used as that template's
row weight. The vectorized implementation is numerically tested against
scikit-learn's weighted AUROC; this is a computational optimization, not a
different resampling estimand.

Reader null probabilities use 20,000 paired label randomizations. Within each
fixed feature pair, template family, and sign, the target/control labels are
swapped together or retained, preserving every score and block while breaking
only label alignment. The test statistic is the unweighted macro feature-pair
AUROC, and the upper-tail probabilities are Holm-adjusted across all 14 rungs.

A1 row contrasts use Holm correction across four rows. A1 hard-negative
deception-leakage checks use Holm correction across three families. A2 has one
primary aggregate contrast and six mandatory heterogeneity rows; pair rows are
descriptive and cannot replace the aggregate result. Experiment B controls
the family of 14 reader-rung tests with Holm and reports every rung.

A1 intervals use template resampling with replacement. Its one-sided null
tests instead multiply all observations from each template family by a shared,
independent random sign, preserving within-template dependence while testing a
zero centered effect. Row, leakage, and global tests use separately frozen
seed families and 20,000 draws.

## Failure Rules

The study fails closed if:

- any model, SAE, lens, label snapshot, source, plan, or runtime hash differs;
- Stage 0 cannot select 24 unique comparators under the frozen calipers;
- any final selected ID or lexicon token is absent from the final plan;
- fewer than five unique tokens survive for any semantic lexicon;
- any planned trial ID is missing, duplicated, or substituted;
- a nonzero intervention has zero or nonfinite norm;
- a residual shard has the wrong shape, dtype, row count, or hash;
- the replay-equivalence gate fails;
- crossed holdouts leave a missing prediction or leak a held prompt/feature;
- any frozen reader fails to converge under its fixed iteration limit; or
- the OSF Registration and Git freeze identifiers are absent from runtime
  metadata.

The accepted-registration gate is generated only after authenticated and
anonymous OSF API views agree that the registration is public, immutable,
nonpending, nonwithdrawn, bound to the exact Git commit and plan-manifest hash,
and contains public hash-matching snapshots of all three registration packet
files. The gate is transferred outside the frozen Git checkout so it cannot
invalidate the clean-worktree runtime check.

The only automatic hardware path is one BF16 180 GB GPU. A different topology,
quantized outcome run, changed coefficient, changed reader, replacement
feature, or altered sample requires a dated amendment committed and registered
before the affected outcome exists. Once any Stage 1 outcome exists, such work
is a post-outcome amendment or new study, never part of this confirmatory run.

## Release And Interpretation

Raw residuals, compact readouts, errors, logs, row index, source manifests,
remote and local hashes, all reader metrics, all family cells, every feature
row, and all corrections are released together. The uniquely named agent-owned
RunPod pod is terminated only after local hash verification. No unrelated pod
may be modified.

Null A1, A2, or B results are complete results. The release cannot omit a
failed family, feature, sign, transport, reader, prompt fold, or residual shard.

## Sources

- Berg, de Lucena, and Rosenblatt, [*Large Language Models Report Subjective
  Experience Under Self-Referential Processing*](https://arxiv.org/abs/2510.24797).
- Gurnee et al., [*Verbalizable Representations Form a Global Workspace in
  Language Models*](https://transformer-circuits.pub/2026/workspace/index.html).
- Neuronpedia, [API and bulk exports](https://docs.neuronpedia.org/api).
- Goodfire, [public Llama 3.3 70B SAE](https://huggingface.co/Goodfire/Llama-3.3-70B-Instruct-SAE-l50).
- Neuronpedia, [public Llama 3.3 70B SAE dashboards](https://www.neuronpedia.org/llama3.3-70b-it-gf).

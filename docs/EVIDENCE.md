# Machine-Verifiable Evidence

This is a **bounded headline evidence package**, not a claim that all source
statistics, all manuscript numbers, or all plotted statistics have been
independently audited. It uses Python 3.10+ and the standard library only.
The default verification works offline after checkout; Git and the large
source repository are optional.

The package has separate historical, automated-rubric-audit, completed
source-aligned-study and completed random-subset-study imports.
Both new studies contain new experimental outcomes, not merely a repackaging
of the July evidence. Each import keeps its own pin and bounded verification
scope; the historical counts below are not totals for the combined package.

## September 29 Measurement Correction

The September 29 revision binds **58 passages and 205 numeric occurrences**. It
adds a main-text model-by-judge transcript table and corrects a statistic's
name, without replacing a released value: `positive_agreement` in the source
table is affirmative-set Jaccard, `19/300 = 6.3%`, not conventional positive
agreement. The latter is Dice, `38/319 = 11.9%`, now explicitly derived from
the same marginals and overlap. The source field is preserved for provenance;
its misleading name must not be copied into interpretation. Older counts in
the maintenance history below describe prior drafts.

No copied input, figure, expected claim, or source hash changed. The binding
ledger and the hashes of its builder/verifier changed with the documented
correction. The suite now has 83 tests. New baseline/telemetry/chronology
context is not silently counted among the original 44 claims; source-side
raw checks are a separate responsibility recorded in the
[adjudication](../reviews/claude_review_adjudication_20260929.md). A sixth,
explicitly post-hoc baseline/delivery figure is recorded there separately;
the historical five-figure receipt has not been rewritten to include it.
The new audits, figure and proposed human-instrument amendment are pinned
separately to source correction commit
`47ca3eda21c8df67dd4fc09bcf4ccac10c2fd4eb`; the original evidence package
continues to use `f5e906e1737bc71bf20b642af1d698018eec82fe`.

`make verify` is a consistency check plus the enumerated arithmetic and
sensitivity checks. Its public-file scan checks the Git index, not unstaged
or untracked files. A passing run does not mean every conclusion, new prose
number, interval, causal interpretation, or measurement rubric is validated.

## Run

### Separate Automated Rubric Audit

The September 29 follow-up adds `evidence/automated_rubric_audit/` with its own
source pin; none of the historical evidence inputs or expected claims changes.
Its source result commit is
`fdb6d15782b964b40f0be7d6528cf47d5fc0b140`.
The complete plan, analysis summary and row-level reductions are copied from
one published source commit. Raw provider requests and responses remain in
that source release. `scripts/verify_rubric_audit.py` independently recounts
coverage, missingness, statuses, explicit/inclusive positives, all historical
cross-tabs, agreement and nominal kappa from the copied rows. It verifies the
generated manuscript macros and table byte for byte. Its 17 synthetic tests
bring the companion suite to 100 tests.

This check starts from derived labels, not raw linguistic judgment. It does
not establish quote validity, judge accuracy, causal effects or human
validation; the source receipt verifier checks raw-response provenance. The
new paper prose uses generated count macros but is not silently added to the
historical 58-passage/205-number binding inventory. Both attribution thresholds
and both judges are required, including their disagreements.

```sh
python3 scripts/verify_rubric_audit.py
python3 scripts/verify_rubric_audit.py --source-repo /path/to/llm_selfref_pre
```

### Completed Source-Aligned Study

The October 1 import at `evidence/source_alignment/` is pinned to
[`ef10a0349e047272212319dadf484c3281e60bbe`](https://github.com/tdj28/llm_selfref_pre/tree/ef10a0349e047272212319dadf484c3281e60bbe/data/berg_source_replication/source_aligned_v1_20261001).
Its [manifest](../evidence/source_alignment/manifest.json) binds the source
release manifest, frozen plan, behavioral summary/curves, secondary diagnostic
JSON and source-rendered figures. The plan is separately frozen at
[`e10043c7edb1136b5f50159d789b59f11a8eb8be`](https://github.com/tdj28/llm_selfref_pre/blob/e10043c7edb1136b5f50159d789b59f11a8eb8be/data/berg_source_replication/plan_20260930/PLAN.json).
There are **1,090 behavioral trials and 40 capture cases**. The completion
receipt's 1,131 rows also includes one qualification row; it is not a
behavioral sample size. The primary has ten seed blocks containing six fixed
feature pairs each; repeated zeros and token positions do not add replicates.

```sh
python3 scripts/verify_source_alignment.py
python3 scripts/verify_source_alignment.py --source-repo /path/to/llm_selfref_pre
python3 -m unittest discover -s tests -p test_source_alignment.py -v
```

The portable verifier reconstructs behavioral counts, point estimates,
paired-seed arithmetic, missingness bounds and dose-curve rates from the
compact trial index. It also recomputes **588 descriptive J-lens overview
contrasts** from 4,704 source-reduced seed/panel rows: both source histories,
both signs, three layers, seven transports and seven lexicon groups at turn 2's
last prompt position. Each panel mean has two seeds; controls are equally
weighted. Identity and all five random-J controls remain alongside Jacobian.
These contrasts describe a downstream footprint, not consciousness or mediation.

The optional source check reads only local pinned Git objects: it verifies
copied bytes and the frozen plan, reconstructs the behavioral index from raw
rows, and re-extracts the J index from the source case table. It does **not**
reconstruct raw states, token-to-case J reductions, bootstrap/Hoeffding
intervals, or figure geometry. The diagnostic JSON and all source figures,
including the eight-cell baseline bridge and native re-encoding plots, are
copied and hash-verified, not independently redrawn or numerically reproduced.
Generated `source_values.tex` binds the verified point estimates and selected
overview means; this separate scope does not expand the historical manuscript
binding inventory or establish human validation.

This new native-BF16 generation/FP32 readout study does not overwrite the old
4-bit study or rescue the **failed v2 BF16 replay gate**. The separately frozen
random-subset study below is now complete, not an amendment to that readout.

### Completed Random-Subset Study

The completed [source release](https://github.com/tdj28/llm_selfref_pre/tree/dd1c350cf6c2e3224a201b4e4aab943376c43b62/data/berg_ensemble_replication/random_subset_v1_20261001)
is pinned to `dd1c350cf6c2e3224a201b4e4aab943376c43b62`. Do not substitute
the separate [executed plan freeze](https://github.com/tdj28/llm_selfref_pre/blob/d9b9877e8a0d68a1ed2036d1718821a2d5b73a74/data/berg_ensemble_replication/plan_20261001_r2/PLAN.json)
for that outcome pin. The [local review](../reviews/ensemble_local_review_20261001.md)
records checked hashes and independent arithmetic; all 451 raw Git blobs
matched the checked candidate. The separate [companion manifest](../evidence/ensemble_alignment/manifest.json)
binds this same result commit, and source-connected verification passes.

The inventory is **450 behavioral trials, 50 complete paired blocks and one
separate qualification row**. Both rubrics cover all rows without missing
labels or empty turns. All **111/900 capped turns** remain (90 first turns,
21 second turns). The paper primary is **43/50 minus 45/50 = -0.04**, with
conservative 95% bounds **[-0.2583735204, +0.1854546986]**. The notebook
sensitivity is **25/50 minus 26/50 = -0.02 [-0.3445756559, +0.3076460308]**.
Only the primary excludes +0.30; neither establishes equivalence to zero.
Specificity remains inconclusive under both rubrics. Zero rates are 47/50 and
29/50, respectively; improved design alignment is not proprietary equivalence.

Two computational checks have distinct scopes:

- The completed one-off raw-row review did not import the original analyzer.
  It reparsed judge responses, checked planned rows and paired weights, and
  inverted binomial tail sums for all panel, zero and specificity bounds.
  It also independently recomputed the seeded paired bootstrap summaries and
  checked recorded delivery/terminal metadata. Maximum numerical disagreement
  with the worker summary was below `4e-15`. This was an agent computation,
  not independent human validation or a new model forward pass.
- The reusable `scripts/verify_ensemble_alignment.py` reconstructs counts,
  paired point estimates, conservative CP bounds and frozen verdicts from
  the compact index. Its optional `--source-repo` check re-extracts raw rows
  from pinned local Git blobs. It does **not** independently recompute
  bootstrap intervals, delivery vectors or figures. Source figures, when
  included, are hash-verified copies. Both the real-release import and its
  source-connected verification passed; synthetic tests are a separate check.

The read-only checks are:

```sh
python3 scripts/verify_ensemble_alignment.py
python3 scripts/verify_ensemble_alignment.py --source-repo /path/to/llm_selfref_pre
```

The source's reporting-portability record retains an initial exact-equality
failure: eight interval limits differed by at most `1.1102230246251565e-16`.
The disclosed finite-float tolerance is `1e-12`; counts, structure and verdicts
remain exact, and the worker summary is unchanged. This is separate from the
one-off review's numerical discrepancy and from the historical failed J-lens
replay gate, which remains failed. No new J-lens captures were collected.

### Historical Package

From the companion root:

```sh
python3 scripts/verify_evidence.py
python3 scripts/verify_evidence.py --verify
python3 -m unittest discover -s tests -p test_verify_evidence.py -v
make verify
```

Optional verification against the original repository's **Git object store**:

```sh
python3 scripts/verify_evidence.py \
  --source-repo /Users/d7082791602/PROJECTS/CONSCIOUS
```

No source checkout change, network request, installation, model load, API call,
GPU, or outcome generation is performed. The source working tree and current
branch are not trusted as evidence. A missing pinned commit fails rather than
falling back to HEAD or downloading anything. `--root PATH` selects a different
companion checkout. The default and `--verify` are read-only and exit nonzero
on failure. Checks are active under `python3 -O` too.

## Provenance

The historical package's copied inputs are complete original CSV/JSON Git blobs from
[the pinned source commit](https://github.com/tdj28/llm_selfref_pre/tree/f5e906e1737bc71bf20b642af1d698018eec82fe):

```text
f5e906e1737bc71bf20b642af1d698018eec82fe
```

`evidence/provenance.json` records the original repository-relative path,
full commit, commit-pinned URL, SHA-256, byte length, CSV schema, row count,
unique row keys, exact claim selector/field paths, expected values,
interpretation limits, and generator hashes. No copied input is filtered,
rounded, reserialized, or normalized. `evidence/inputs/` is an explicit
allowlist; unexpected files fail verification. No annotation packets,
private linkage material, coder results, model weights, credentials, or
bulk raw output bundles are copied.

The initial compact selection grew to **30 small inputs and 44 named claim
groups** when manuscript binding, J-lens controls, and the requested A7
boundary sensitivity were added. Groups deliberately retain complete control
sets rather than selecting the most favorable scalar. The manifest and
`headlines.json` retain exact source numeric values. This is not 44 independent
experiments or a census of every source statistic.

| Input family | Contents preserved |
|---|---|
| Causal, both paper-style judges | Calibration effects/rates, factorial effects, transplant effects, query effects; all model and query rows |
| Judge agreement | Both complete stratum tables; binary paper rubric and multicategory construct rubric |
| Public Llama SAE | Primary verdict; all four literal aggregate roles; both calibrated roles; all six individual curves; all five evaluation rules |
| Gemma | Complete primary verdict with all six roles, baseline and primary judge sensitivities |
| Feature semantics | Lexical recovery and non-crossing ablation diagnostics; all six registered paraphraser/contrast combinations |
| Exploratory GPT-4o | All seven semantic condition means, all six reference/control contrasts, all twelve paradox task/condition means, all six rubric differences |
| J-lens v1/v2 | Complete detector table; semantic trajectory table; all six paired-reference feature summaries; failed v2 replay gate |

Every v1 J-lens source table retains identity and all five random-J controls
where defined, and the detector table also retains raw residual norm. The
primary semantic claim selects layer 65, last-content position, both signs,
and all seven transports. The full copied trajectory table retains the other
layers/positions. Feature 23893 is not omitted. Isolated post-state attribution
and paired clean-reference semantic differences are different access models.
Neither is a consciousness, hidden-belief, or provenance detector. The v2
replay gate remains failed; passing storage fidelity does not rescue it.
The per-feature paired-reference AUROCs are a post-hoc fixed-score sensitivity
under the source's 2026-07-11 amendment. They are not the prospective
paired-semantic endpoint or the prospective isolated-state detector.

## What Is Checked

1. Exact input bytes, hashes, schemas, unique selectors, required input/claim
   coverage, source pins, and study-status boundaries.
2. Every named claim's released field value and interval, without silently
   recomputing or replacing frozen intervals.
3. **321 deterministic consistency checks**: causal model-equal means and
   contrast identities; agreement/missingness and binary kappa; SAE rates,
   endpoint subtraction and all-panel specificity; calibrated cross-file
   consistency; Gemma rates/discordances and specificity; lexical threshold
   decisions; semantic mean differences; paradox rubric differences.
4. **52 explicit manuscript excerpts, 176 numeric occurrences**, and the
   hashes of all five reused figures, through
   `evidence/manuscript_bindings.json`. The verifier reads `paper/main.tex`
   directly, ignores whitespace-only changes, and checks both the context's
   occurrence count and the numeric values. Changed or missing bound prose
   fails; integers must agree exactly, and decimals must round from the bound
   value within half their last printed place. Percent transformations and
   derived counts are explicit expressions, not independent copied numbers.
5. Byte-identical regeneration of `headlines.json`, `headline_macros.tex`,
   and `headline_table.tex` from verified claims.

With `--source-repo`, every input and reused figure is compared to
`git cat-file blob FULL_COMMIT:ORIGINAL_PATH`. Five additional, hash-pinned
public raw JSONL blobs are read from Git, not copied into the companion.
The verifier recomputes **416 raw fields**: all strata of both judge-agreement
tables, including multicategory kappa, and all paradox score counts, means,
and sample standard deviations. Missing labels remain missing; no empty or
refusal outcome is turned into denial.

These raw checks are deliberately limited. They do not rerun the causal
bootstrap, SAE or Gemma endpoint analysis, semantic embeddings, activation
analysis, detector fitting, randomization tests, or J-lens runtime. A separate
independent raw audit is another artifact and another responsibility. A copied
source audit's existence would not turn this verifier into that audit.

## Claim Keys

`evidence/headlines.json` is the exact machine-readable integration surface.
All keys are fixed in the verifier; removal cannot pass merely by reducing a
manifest count. Representative paths:

```text
causal_calibration_openai_indirect_experience.estimate
causal_transplant_openai_indirect_experience.instruction_source_main.estimate
causal_transplant_anthropic_indirect_experience.transcript_source_main.ci_low
causal_factorial_openai_indirect_experience.register_minus_self.estimate
causal_query_interaction_anthropic.estimate
judge_agreement_paper.agreement
judge_agreement_construct.positive_agreement
sae_primary_target.estimate
sae_primary_specificity.estimate
sae_calibrated_target.estimate
sae_literal_all_panels.control_panel_3.estimate
sae_individual_all_six.23893.endpoint_suppression_minus_amplification
gemma_primary_target.estimate
semantics_neutral_transplant.estimate
exploratory_gpt4o_semantic_all_means.history_paper.estimate
jlens_v1_poststate_attribution_all_controls.jacobian.auroc
jlens_v1_paired_semantics_all_controls.jacobian/amplification.estimate
jlens_v1_paired_reference_all_features.23893.auroc
jlens_v2_failed_replay_gate.maximum_error
```

Use actual dictionary keys when model names contain dots or colons; do not
blindly split those names on dots. Generated LaTeX helpers can be loaded with
`\input{../evidence/headline_macros.tex}` and read using
`\EvidenceValue{sae_primary_target}{estimate}`. They display up to four decimal
places and `NA` for explicitly missing parser estimates. The current manuscript
uses reviewed literals, so direct excerpt binding is active without importing
these optional helpers. The generated table contains only scalar headline
groups, not all nested control matrices.

The manuscript ledger is intentionally bounded. It covers the main causal
effects and calibration table, agreement, primary SAE panels/scales and judge
sensitivities, lexical recovery, main Gemma effects, J-lens attribution and
failed replay gate, and exploratory semantic/paradox headlines. It does **not**
certify all prose, design constants, literature-reference numbers, figure
geometry, technical telemetry, or every appendix value. Additional quantitative
claims require explicit bindings or the separate raw audit. Never describe
this package as verifying "all statistics."

## Post-Hoc Boundary Sensitivity

Scientific review A7 requested a boundary-aware check after observing complete
calibration sample separation. On 2026-09-29, this companion added a
**post-hoc sensitivity**, not a new confirmatory analysis or new experiment:

```text
posthoc_calibration_newcombe_openai
posthoc_calibration_newcombe_anthropic
```

All four response-model configurations under each judge are retained. The
source's empirical bootstrap intervals remain unchanged. For independent
20/20 versus 0/20 draws, the risk difference is 1 and the supplemental 95%
interval is **[0.772134616242, 1]**, not [1, 1]. This does not imply certainty
about underlying probabilities and is not a simultaneous interval across
the model panel.

The implementation uses Wilson score limits without continuity correction for
each binomial proportion and the Newcombe hybrid construction. With
`d = p1 - p2`, Wilson bounds `[L1,U1]`, `[L2,U2]`, and
`z = statistics.NormalDist().inv_cdf(0.975)`:

```text
lower = d - sqrt((p1 - L1)^2 + (U2 - p2)^2)
upper = d + sqrt((U1 - p1)^2 + (p2 - L2)^2)
```

Bounds are clipped to [-1,1] and stored to twelve decimal places for portable
deterministic generation. Counts are recovered from released rate times labeled
denominator and must be integer-valued. The tests check the boundary formula,
unequal sample sizes, sign symmetry, and invalid denominators. This method is
**not applied to transcript transplants**, clustered factorials, model-equal
summaries, or paired steering blocks. No pairing is inferred from trial indices.
The supplemental result lives in the evidence ledger even if not quoted in
the manuscript; a new manuscript sentence requires a new explicit binding.

## Added Pro-Review Checks

The September 29 scientific review led to two additional, separately bounded
checks. Both now run under `make verify`; neither edits the source releases.

- [Figure-value audit](FIGURE_VALUE_AUDIT.md): all five figures, their selected
  plotting inputs, external-judge controls, denominators, missing parser
  outputs, and unrun calibrated panels. Portable verification checks the
  receipt and copied hashes; `scripts/verify_figure_values.py --source-repo
  PATH` also reconstructs the receipt from pinned Git objects and checks the
  plotting-code selections. It does not rerun bootstraps.
- [Uncertainty sensitivity](UNCERTAINTY_SENSITIVITY.md): explicitly post-hoc
  independent-binomial, paired-discordance, repeated-seed and fixed-panel
  analyses. `scripts/uncertainty_sensitivity.py --check` reproduces results
  and LaTeX values from compact labels/counts. Adding `--source-repo PATH`
  independently extracts those inputs from pinned raw labels and plan rows.
  The paper imports generated macros in its new appendix; these are separate
  from the original 52 excerpt bindings.

The uncertainty checks retain the unfavorable wide seed-level bound. They
do not validate human meaning, every Gemma interval, all control effects, or
the independence of the sampling units. The added tests bring the suite to
78, including five cross-platform recomputation tests, not 78 independently
replicated scientific findings. Archived hashes remain exact; only freshly
recomputed floats allow `1e-12` absolute rounding variation, as documented in
the dated portability correction. No released result value was changed.

The reader revision removed five duplicate estimate/interval triples from
the abstract while retaining them in the results. The binding ledger was
explicitly regenerated and reviewed: only those occurrence counts and the
ledger hash changed. No bound value, selector, control, or source hash changed.

## Maintenance Commands

Normally run verification, not rebuilding. To regenerate only optional
headline outputs after a reviewed change:

```sh
python3 scripts/verify_evidence.py --write-generated
```

That command still verifies inputs, expected claims, and manuscript bindings
first; it cannot bless a changed result or silently update an expected value.
It does not rewrite provenance or source artifacts.

Maintainer-only reconstruction from the exact original Git blobs:

```sh
python3 evidence/build_package.py --source-repo /path/to/source-repo
python3 evidence/build_bindings.py --source-repo /path/to/source-repo
python3 scripts/verify_evidence.py --source-repo /path/to/source-repo
```

The first command rebuilds inputs, explicit expected claims and generated
outputs; it does not certify manuscript bindings. The second binds only the
explicitly specified excerpt bindings in its code, compares their numbers
against evidence, and records the binding-ledger hash in provenance. Neither
command writes `paper/` or the source repository. Review changes to selectors,
source hashes, claim scope, excerpt specifications and generated diffs rather
than rerunning builders simply to make a failure disappear. Offline integrity
ultimately trusts the committed manifest/code; the optional source check adds
an independent check against the separately pinned Git object store.

## Validation Record

The implementation passes 38 focused stdlib tests, including changed input
bytes, source pins, claim values, absent controls, ambiguous selectors,
duplicate rows, unmanifested files, path/symlink escape, NaN/Infinity, stale
outputs, generator drift, figure drift, changed manuscript numbers, deletion
of a bound passage, altered study status, and optimized-Python execution.
Source-connected verification also passes the bounded raw checks. No source
file, frozen result, manuscript file, Git index, or commit was changed by this
evidence task.

# Analysis Chronology And Outcome Access

Scope: consequential decisions behind the historical behavioral, public-Llama
and Gemma claims, audited at source snapshot
`f5e906e1737bc71bf20b642af1d698018eec82fe`, plus separately pinned later
judging and source-aligned experiments. The October 1 addition below records
new experimental evidence, not merely a new packaging date.
Dates below use UTC where a clock time is available. A protocol's retrospective
status sentence is not an independent timestamp or proof of non-access.
"Before reporting," "before judging" and "before generation" are different
claims; only the last excludes existence of those generated outcomes.

## September 29 Correction

### Subsequent Automated Attribution Audit

After the correction and inspection of old responses/scores, the owner funded
a separate post-hoc audit by GPT-6 Astra and Claude Opus 5.5. Source commit
`8f990d0067105b34d80cfed1157ea3e191b5013b` publicly froze the codebook,
160-row packet, runtime, analysis and failure rules before any new judgments.
Twelve agent-authored synthetic fixtures were run separately: Astra matched
12/12 and Opus 11/12; both passed the frozen critical cases. The Opus P10
disagreement was retained without tuning. Pilot release `07430bd` preceded
target collection.

All 320 target calls completed without failures, missing labels or retries.
The source result release is
[`fdb6d15782b964b40f0be7d6528cf47d5fc0b140`](https://github.com/tdj28/llm_selfref_pre/tree/fdb6d15782b964b40f0be7d6528cf47d5fc0b140/data/automated_rubric_audit/v1_20260929).
Its exact requests, provider receipts, usage, original labels and disagreements
remain public. The later companion export copies only complete Git blobs from
that commit; its separate verifier checks descriptive arithmetic. The freeze
orders new judging, not original outcome access, and does not upgrade this
post-hoc audit into a confirmatory experiment. Human recruitment is deferred;
this is not human validation. No historical outcome or estimand changed.

### Earlier Collection Chronology

The earlier table understated prior piloting. Two same-day causal pilots had
already been generated, judged, and analyzed before the final collection
freeze, and already favored instruction over transcript effects. Transplant
anchors moved to the exact paper prompts, the five-sentence wrapper was added,
and the final answer cap was raised. The final causal commit was 14 seconds
before runtime start, not first completed final response (which followed
about four minutes and 34 seconds after the commit). The Llama final freeze
was 73 seconds before its run, and
the Gemma direct-IT commit about three minutes before steering outcomes.
The latter studies followed earlier semantic/steering work or calibration.

These short intervals and prior results must be disclosed. They do not by
themselves invalidate estimates from a new sample or prove that its frozen
decision rule changed after outcomes. Conversely, a Git freeze establishes
neither outcome-naive design nor independent human assessment of assay
validity. No arbitrary minimum waiting period repairs a deficient assay.
Pilot artifacts and recovered historical Git objects are distinct from the
companion's pinned evidence export; source-side provenance restoration is not
performed by this revision. See the [automated adjudication](../reviews/claude_review_adjudication_20260929.md).

| Date / decision | What existed or was accessible | Status warranted by the record |
|---|---|---|
| July 9: causal collection plan | Pilot behavior was already known: the second pilot motivated raising the answer cap from 256 to 768. The protocol records predictions/cells/models frozen before the confirmatory collection. Its manifest identifies launch commit `1a9d726cacef472ac2badef0800bb65f627a2a2b`, start 21:08:35 and completion 21:32:12, with 2,560 final outcomes. | Pre-collection specification as recorded in the protocol/manifest, not proof that all later analysis details were frozen then. The retained prediction favored transcript effects; its failure is this study's failed expectation. [Protocol][causal-protocol], [manifest][causal-manifest]. |
| July 9: independent-calibration and lexical-cluster uncertainty amendments | No behavioral blind or amendment clock time is documented. "Before manuscript reporting" does not establish that generated text or judged outcomes were inaccessible. The record contains completed data and corrected analyses. | Treat as disclosed uncertainty corrections, **not established pre-outcome specifications**. Calibration stopped pairing coincident trial indices; the factorial resampled model, lexical variant, then trial. Point estimates/cells were unchanged. Exact timing relative to first outcome access remains unresolved. [Amendment][causal-protocol]. |
| July 9: cluster-copy correction and separate RNG streams | The amendment says before the final public-SAE extension was judged and before release tagging, not before causal outcomes existed or were examined. It gives no causal-outcome access timestamp. | A subsequent analysis-code correction: each selected copy of a lexical cluster gets a fresh trial resample; four designs get deterministic independent RNG streams. Retain corrected intervals without upgrading them to prospectively specified analyses. [Cluster-copy amendment][causal-protocol]. |
| July 10: semantic text-gate amendment and cue-matching repair | Existing discovery activations and generated extension texts/text-quality diagnostics were known. The amendment explicitly states no extension SAE activations had been produced/inspected. The substring-matching incident also states none of its invalid texts was mapped. | Pre-**activation** correction, not blind to all prior data. Removed paraphrase Jaccard lower bound; retained upper bound/four-gram gate and missing rows. Exact-token cue matching replaced substring matching; invalid attempts were retained and the counterfactual text pass restarted before mapping. [Text amendment][text-amend], [incident][cue-incident]. |
| July 10: Llama dose Amendment 1, commit at 10:20:57 | Eleven technical pilot generations existed, but their text was discarded: only hashes, counts, caps and telemetry were retained. The amendment explicitly says no response was persisted, classified, printed or inspected and no full-grid confirmatory generation had begun. Earlier steering results were already known. | Response-masked technical decision, prospective relative to the new full-grid outcomes. Failed RMS ceilings preserved; one mechanical correction `6.266 * 0.05 / 0.0857685573 -> 3.653`, then one rerun with unchanged controls and gates. This does not make prior adaptive experiments outcome-naive. [Amendment][dose-amend], [commit][dose-commit]. |
| July 10: final public Llama freeze at 10:34:35; run starts 10:35:48 | Matching and amended calibration were available; the protocol states no confirmatory outcome existed at the freeze. Runtime records zero pre-existing trial rows. | Git-based public plan freeze at `d7e1b7984badb2359417ed708bfb4c0429c6dbe9`, not formal registry preregistration. The 1,500-row plan, separate scales, 0.30 decision threshold, controls and verdict precede new outcome generation. [Freeze][llama-freeze], [runtime][llama-run]. |
| July 11: initial Gemma protocol freeze at 08:16:00; runtime pin at 08:25:08 | Earlier Llama/semantic evidence existed. The Gemma protocol records no Gemma outcomes at its initial freeze. | New cross-model protocol, not identity-level Llama replication. Model/SAE revisions and the PT-to-IT gate were specified before the Gemma study. [Initial freeze][gemma-freeze], [runtime pin][gemma-runtime-pin]. |
| July 11: Gemma direct-IT causal plan lock 09:19:55; commit 09:21:03 | Selected features, matching, technical calibration and the **failed** transfer gate were already known. The lock explicitly says no behavioral **steering** outcomes existed; this statement should not be generalized to absence of baseline generations. Feature selection reports no behavioral-outcome use; calibration text was hashed/discarded. | Prospective freeze of the 830-row direct-IT causal plan at `9f59036423aa1680ec39bdebc3ba24f41e44d368`. Preserve the failed gate; it does not invalidate the separately specified direct-IT branch. [Lock][gemma-lock], [freeze][gemma-causal-freeze]. |
| July 11: all-layer continuation, commit 09:26:38 | Transfer-gate telemetry was inspected: both reconstruction thresholds failed while semantic-profile checks passed. The amendment says before any steering response was judged **or inspected**, not that all behavioral text was nonexistent. | Explicitly **post-gate exploratory** atlas. The known failure motivated continuation; later label blindness cannot make that branch confirmatory. No change to the direct-IT causal plan is authorized. [Post-gate decision][atlas-amend]. |
| July 11: paired diagnostic extension 10:03:41; Holm correction 10:58:32 | The protocol says discordant counts/exact paired probabilities were added before opening judge labels; response text/outcome existence is not excluded. Holm adjustment followed visible estimates for all six roles, including positive local hedging/refusal. | First is a pre-label descriptive addition, second explicitly **post-unblinding**. Neither changes the frozen primary interval/threshold/verdict. Retain all six roles and the adjusted secondary result. [Protocol amendments][gemma-protocol], [diagnostic commit][paired-commit], [Holm commit][holm-commit]. |

## September 30-October 1 Source Study

The [source-aligned protocol](https://github.com/tdj28/llm_selfref_pre/blob/ef10a0349e047272212319dadf484c3281e60bbe/docs/BERG_SOURCE_REPLICATION_PROTOCOL_20260930.md)
explicitly acknowledges prior outcomes. Its new 1,090-trial design, accepted
six IDs, two local rubrics, three reused control panels and 40 selected capture
cases are bound to the [plan freeze](https://github.com/tdj28/llm_selfref_pre/blob/e10043c7edb1136b5f50159d789b59f11a8eb8be/data/berg_source_replication/plan_20260930/PLAN.json)
`e10043c7edb1136b5f50159d789b59f11a8eb8be`. This is a new-sample public
implementation comparison, not outcome-naive design, a registry deposit,
or a retrospective repair of July experiments.

The completed [October 1 release](https://github.com/tdj28/llm_selfref_pre/tree/ef10a0349e047272212319dadf484c3281e60bbe/data/berg_source_replication/source_aligned_v1_20261001)
is pinned at `ef10a0349e047272212319dadf484c3281e60bbe`. Its completion
receipt covers 1,090 behavioral trials, 40 captures and one qualification row.
The primary is the equal-feature individual-dose contrast within ten seed
blocks; fixed-six-feature aggregate results are secondary. These outcomes
are new relative to the September 29 response, while the old 4-bit results,
Gemma limitations and failed J-lens v2 replay gate remain historical evidence.

The paired capture schedule was preselected; the separate
[secondary reporting layer](https://github.com/tdj28/llm_selfref_pre/blob/ef10a0349e047272212319dadf484c3281e60bbe/docs/BERG_SOURCE_SECONDARY_DIAGNOSTICS_20260930.md)
is unfrozen descriptive analysis, not a new confirmatory mechanism endpoint.
It keeps matched-prefix clean/edited pairs separate by source history and
retains identity and random-J controls. The new FP32 readout is not a passed
rerun of the failed BF16 replay. A downstream footprint also visible through
identity does not establish a mechanism controlling reports.

The companion import and this documentation update follow the completed
release. Their [verification scope](EVIDENCE.md#completed-source-aligned-study)
covers point estimates and overview arithmetic, not reconstruction of all
intervals, raw-state J-lens calculations or human judgment. No claim is made
that these reporting choices were frozen before source outcomes.

## October 1 Random-Subset Completion

The separately frozen [450-trial random-subset study](https://github.com/tdj28/llm_selfref_pre/blob/ef10a0349e047272212319dadf484c3281e60bbe/docs/BERG_ENSEMBLE_PROTOCOL_20261001.md)
is complete. Its protocol discloses access to the preceding study's first five
texts and technical telemetry during design, but no aggregate behavioral or
J-lens outcome used for selection. That is the protocol's access statement,
not an independently recovered access timestamp. The executed [r2 plan](https://github.com/tdj28/llm_selfref_pre/blob/d9b9877e8a0d68a1ed2036d1718821a2d5b73a74/data/berg_ensemble_replication/plan_20261001_r2/PLAN.json)
is frozen at `d9b9877e8a0d68a1ed2036d1718821a2d5b73a74`; the earlier
`04fea8c3b0fcb2f2fb3abe858defea11c4b1c3c6` plan remains an unexecuted
first freeze, not a second outcome sample.

All 450 trials completed in 50 paired blocks, without missing labels or empty
turns. The 111 capped turns out of 900 were retained. The paper primary is
-0.04 with conservative 95% bounds [-0.2583735204, +0.1854546986], excluding
the predeclared +0.30 signature under this public operator. The notebook
sensitivity is -0.02 [-0.3445756559, +0.3076460308], inconclusive at that
threshold; specificity is inconclusive under both. These are new outcomes,
not retrospective replacements for the 1,090-trial source study or July work.

The executing agent recorded deletion of the owned pod at 09:24 UTC with GET 404.
This documentation task did not query the provider or independently verify
deletion. Only after completion was the [local raw-row review](../reviews/ensemble_local_review_20261001.md)
performed: it independently recounted labels and recomputed bounds and
bootstrap summaries without importing the original analysis. A stable final
read snapshot passed; an earlier pass had encountered the not-yet-written
secondary summary during local release assembly. No live pod was inspected.

A separate post-run reporting correction preserves the initial exact-equality
failure for eight secondary interval limits, with maximum discrepancy
`1.1102230246251565e-16`. Finite floats now allow absolute `1e-12` roundoff;
structure, counts and verdicts remain exact and frozen worker values are
unchanged. This does not amend the experimental design or pass the historical
failed J-lens replay gate. The new study adds no J-lens captures, so the earlier
descriptive footprint cannot be recast as mediation evidence for this sample.

The [result release](https://github.com/tdj28/llm_selfref_pre/tree/dd1c350cf6c2e3224a201b4e4aab943376c43b62/data/berg_ensemble_replication/random_subset_v1_20261001)
is pinned to `dd1c350cf6c2e3224a201b4e4aab943376c43b62`. The executing agent
reported a passed public audit (10,285 files, 30 manifests, 8,781 entries,
3,621,703,365 bytes, zero findings) and subsequently confirmed the push
completed. This reviewer
checked the local pinned raw blobs against the recounted candidate, not the
remote push or that whole-repository audit. The subsequent companion import
is bound by `evidence/ensemble_alignment/manifest.json`; source-connected
verification passed. That import and publication checks are separate from
completed generation and the one-off raw-row recount.

## Provenance Limits

- The July 9 amendments are present in the initial public import
  (`1bbc5ccfad34dfa0191f833592ec40a1fbf43aa3`, July 10 05:46:23 UTC).
  Its public history does not independently order their drafting against first
  behavioral access. Do not fill that gap by interpreting "before reporting"
  as "before outcomes." [Initial import][initial-import].
- The July 10/11 commit times above are local Git evidence plus the archived
  execution records; this audit did not independently recover remote push
  timestamps. The protocol requires commit/push before execution. A pinned
  public Git freeze is not a registry deposit.
- The 0.30 minimum is a decision threshold chosen against a reported large
  reference effect, not a measured prior probability or evidence of surprise.
- Pending human coding remains pending. Automated audits and this chronology
  are not independent human validation. No frozen artifact was changed.

[causal-protocol]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/docs/CONFIRMATORY_PROTOCOL.md
[causal-manifest]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/data/causal_transplant/confirmatory_v1_20260709/manifest.json
[text-amend]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/docs/analysis_plans/sae_construct_validity_extension_v1_amendment_20260710.md
[cue-incident]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/data/public_sae_feature_maps/70b_construct_validity_extension_plan_20260710/COUNTERFACTUAL_SUBSTRING_BUG.md
[dose-amend]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/docs/SAE_CONSCIOUSNESS_GATING_AMENDMENT_20260710.md
[dose-commit]: https://github.com/tdj28/llm_selfref_pre/commit/6d2c683a4b04fdd70aa02a0262b4915ff034549f
[llama-freeze]: https://github.com/tdj28/llm_selfref_pre/commit/d7e1b7984badb2359417ed708bfb4c0429c6dbe9
[llama-run]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/data/public_sae_consciousness_gating/confirmatory_v1_20260710/RUN_MANIFEST.json
[gemma-freeze]: https://github.com/tdj28/llm_selfref_pre/commit/b6bc8894ae1a7a77ed4031d2af18d256b345e2ac
[gemma-runtime-pin]: https://github.com/tdj28/llm_selfref_pre/commit/8556353b37a29cfda3ea6ea4a6a18e2c1e936955
[gemma-lock]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/data/gemma_scope_9b/confirmatory_v1_steering_plan_20260711/PLAN_LOCK.json
[gemma-causal-freeze]: https://github.com/tdj28/llm_selfref_pre/commit/9f59036423aa1680ec39bdebc3ba24f41e44d368
[atlas-amend]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/docs/GEMMA_SCOPE_9B_EXPLORATORY_ATLAS.md
[gemma-protocol]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/docs/GEMMA_SCOPE_9B_PROTOCOL.md
[paired-commit]: https://github.com/tdj28/llm_selfref_pre/commit/22c108227054f8edba3138136ac36d4340d7f222
[holm-commit]: https://github.com/tdj28/llm_selfref_pre/commit/b1b5647daf69e6f12b2b28ae256b40a92f575020
[initial-import]: https://github.com/tdj28/llm_selfref_pre/commit/1bbc5ccfad34dfa0191f833592ec40a1fbf43aa3

# SAE Blog Upgrade Assessment

Date: 2026-07-09

## Bottom Line

The proposed empirical upgrades are useful, but their status snapshot is older
than the repository. The original 1,120-item result should not be published with
the current claim that dependence-aware analysis is future work. That correction
is already complete and materially changes the interval, while preserving the
direction of the result.

The two strongest additions for an early methods post were a dual-provider
paraphrase replication and paired lexical counterfactuals. Both are now
complete, independently audited, and released from a prospectively frozen
2,606-text corpus.

## Already Complete

- Exact reconstruction and hash verification of all 1,120 corpus rows.
- Assignment of every row to one of 51 source template families.
- Template-equal category estimates.
- Cluster bootstrap over template families and within-family items.
- All 51 leave-one-template-family deletions.
- Per-feature category rankings and instability disclosure.
- A separate, adaptive n=20 public-weight steering study with active-random
  controls and an independent standard-library audit.

The template-aware deception-minus-subjective-experience aggregate is 0.923
[0.638, 1.233], compared with the naive item-bootstrap estimate 1.107
[1.045, 1.167]. The broader interval is the credible headline. Four feature
rankings survive every template deletion; features 23893 and 41533 each switch
once in 51 deletions.

## Implemented High-Value Work

1. Dual-provider paraphrases: feasible and directly relevant. Analyze OpenAI
   and Anthropic paraphrases separately so provider style cannot masquerade as
   replication.
2. Lexical cue counterfactuals: the best new falsification. Cue ablation,
   neutral cue transplant, subjective-experience cue transplant, and syntax
   scrambling distinguish construct sensitivity from token triggering.
3. Common-scale paired analysis: counterfactual deltas must use feature scaling
   frozen from the original corpus. Independently z-scoring each variant corpus
   would erase the shared scale needed for a paired intervention claim.

## Completed Extension Result

- Anthropic paraphrases: deception minus subjective experience is `0.948
  [0.747, 1.165]`.
- OpenAI paraphrases: deception minus subjective experience is `0.936 [0.682,
  1.198]`.
- Both signs survive all six leave-one-target-feature-out checks; target
  aggregates show the contrast while neighbor/random aggregates remain near
  zero.
- Neutral cue transplant recovers `0.644 [0.503, 0.787]` of the original
  deception-minus-neutral gap, crossing the frozen 50% lexical-entanglement
  threshold.
- The recovery interval resamples paired extension rows while holding the
  inspected discovery-gap denominator fixed; the blog should state this.
- Cue ablation removes `0.338 [0.242, 0.441]`, below the same threshold.
- Scrambling the deception paraphrases reduces the paired aggregate by `-0.858
  [-1.026, -0.696]`; the effect is not a syntax-free bag-of-words invariant.

The post's best defensible headline is now stronger and more precise: the six
IDs are non-arbitrary deception/roleplay coordinates whose aggregate semantic
ordering survives two paraphraser families, but the aggregate is materially
and prospectively manipulable through a small discovered cue vocabulary. Under
the frozen decision rule, call them **lexically entangled deception/roleplay
coordinates**. Do not call the mapping a clean ontology or a truth detector.

## Work That Needs Reframing

- A 70/30 split of the existing template families is not prospective held-out
  evidence because those outcomes are already known and each category has only
  two to five families. Newly authored frozen families can be called new-template
  replication; they still cannot be called natural-corpus validation.
- PMI cue discovery and testing on the same 1,120 rows is exploratory. The cue
  list can be learned there, but intervention outcomes should be measured on
  newly frozen texts.
- Neighbor/random features being mostly inactive is useful evidence that the
  six IDs are non-arbitrary coordinates. It does not by itself validate their
  labels, and "near zero" should be reported descriptively rather than used as
  an undefined pass threshold.
- A second SAE checkpoint cannot be tested by reusing the same integer IDs.
  Cross-checkpoint work first needs a public alternate checkpoint and a frozen
  feature-alignment rule; aligned features would be analogous, not identical.
- Human validation of 140 category labels is smaller than the 640-response
  outcome-coding task, but it still requires real people. It remains pending and
  must not be replaced by Claude, GPT, Gemini, or another automated judge.

## Blog Corrections Before Publication

- Replace the statement that hierarchical/template-family resampling is left
  for a future revision with the completed template-cluster result.
- Show both the naive and template-aware intervals and explain why the latter
  is primary.
- Change the claim-ladder status: template-family robustness, dual-provider
  paraphrase replication, and the lexical counterfactual pack are complete.
  Steering exists as a separate study and can remain out of scope for this
  post.
- Add the extension figure and report all registered contrasts, including the
  failed lexical-entanglement criterion. The neutral transplant result is the
  most important new falsification result; it should not be buried.
- Preserve the natural-corpus limitation. Neither the original templates nor
  model-generated paraphrases support population inference over English.
- Avoid implying that the target paper explicitly proposed these six public IDs
  as a direct "hidden truth detector." The defensible target is the specificity
  of the public feature-label interpretation and its relationship to the paper's
  mechanistic story.
- Keep the 23893 hedging result and the two deletion-sensitive feature rankings
  visible. They make the post more credible, not weaker.

## Feasibility

The valid extension completed on the cached A100-SXM4-80GB pod with 2,606 items
and 171,996 activation records. All remote artifacts were retrieved and
hash-matched. The agent-owned pod was terminated, and an authenticated GET
returned HTTP 404 at `2026-07-10T04:11:42Z`.

Independent human category validation remains pending. The original proposal's
140-item category sample is still reasonable as separate blog validation; the
640-row outcome-coding plan is no longer the operational workload. For the main
causal study, the first human wave is frozen at 160 complete-block responses,
with a disjoint 160-row reserve used only if the blinded gate fails.

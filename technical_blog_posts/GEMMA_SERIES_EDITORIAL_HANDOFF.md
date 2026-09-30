# Gemma Scope Blog Series: Editorial Handoff

**2026-09-29 correction: drafts not ready for publication.** Four drafts now
carry dated interpretation corrections and `draft: true`. The completed release,
historical numbers, verdict files, and six PNG assets are preserved, not
rewritten. Human instrument validation and editorial approval remain open.
This handoff is an editorial map, not a claim that a human inspected or approved
the artifacts, or a substitute for rendered publication checks.

## Recommended Publication Order

1. **Live foundation:** [How to Read an SAE Feature ID](https://praxagent.ai/blog/posts/how-to-read-an-sae-feature-id/index.html)
2. **Platform primer:** `Gemma_Scope_Is_A_Layerwise_Microscope.md`
3. **Git-frozen causal study with weak target delivery:** `Can_Deception_Features_Steer_Gemma_2_9B.md`
4. **Exploratory layerwise map:** `Where_Do_Consciousness_Report_Features_Appear_In_Gemma_2_9B.md`
5. **Mechanistic follow-up:** `From_Feature_Maps_To_Causal_Relays.md`

This order introduces dictionary-local feature identity before moving from
platform capabilities to the primary causal verdict, then to the explicitly
exploratory atlas, and finally to the narrower causal-relay result.

## Draft And Asset Map

| Draft | Role | Publication assets |
|---|---|---|
| `Gemma_Scope_Is_A_Layerwise_Microscope.md` | Explains the Gemma Scope inventory, JumpReLU mechanics, dictionary-local IDs, and the failed PT-to-IT gate. | Inline Mermaid diagrams; no external bitmap required. |
| `Can_Deception_Features_Steer_Gemma_2_9B.md` | Reports the baseline, primary direct-IT intervention, matched controls, evaluator sensitivity, historical verdict, and weak-delivery limitation. | `gemma_baseline_contrast.png`, `gemma_primary_steering_forest.png` |
| `Where_Do_Consciousness_Report_Features_Appear_In_Gemma_2_9B.md` | Reports the separately labeled post-gate exploratory residual and sublayer atlas. | `gemma_exploratory_layerwise_construct_trajectories.png`, `gemma_exploratory_targeted_sublayers.png`, `gemma_exploratory_cross_layer_feature_links.png` |
| `From_Feature_Maps_To_Causal_Relays.md` | Separates descriptive cross-layer matching from intervention-based downstream propagation. | `gemma_causal_relay.png` |

The publication PNGs are synchronized copies of figures in
`data/gemma_scope_9b/confirmatory_v1_20260711/figures/`. Matching PDFs remain in
the release for print use. Do not edit a copied PNG independently of its source
figure and renderer.

## Authoritative Sources

| Question | Source |
|---|---|
| Concise outcomes and claim boundaries | `docs/GEMMA_SCOPE_9B_RESULTS.md` |
| Prospective decisions and stage gates | `docs/GEMMA_SCOPE_9B_PROTOCOL.md` |
| Primary verdict and specificity | `data/gemma_scope_9b/confirmatory_v1_20260711/analysis/primary_verdict.json` |
| Baseline estimates | `data/gemma_scope_9b/confirmatory_v1_20260711/analysis/baseline_effects.csv` |
| Steering and comparator estimates | `data/gemma_scope_9b/confirmatory_v1_20260711/analysis/steering_effects.csv` |
| Judge-family sensitivity | `data/gemma_scope_9b/confirmatory_v1_20260711/analysis/judge_sensitivity.csv` |
| Relay estimates | `data/gemma_scope_9b/confirmatory_v1_20260711/analysis/relay_effects.csv` |
| Transfer-gate result | `data/gemma_scope_9b/confirmatory_v1_20260711/atlas/transfer_gate.json` |
| Exploratory layer and sublayer summaries | `data/gemma_scope_9b/confirmatory_v1_20260711/analysis/exploratory_layerwise_constructs.csv` and `exploratory_sublayer_constructs.csv` |
| Cross-layer descriptive links | `data/gemma_scope_9b/confirmatory_v1_20260711/atlas_exploratory/cross_layer_feature_edges.csv` and `cross_layer_optimal_assignments.csv` |
| Separately implemented agent raw-row audit, not independent human validation | `data/gemma_scope_9b/confirmatory_v1_20260711/analysis/independent_headline_audit.json` |
| Complete release integrity | `data/gemma_scope_9b/confirmatory_v1_20260711/release_manifest.json` |

The result-bearing release was published in commit `19a4cd1`; manifest binding
was published in `91aa504`. Draft provenance commits are `02e4280` (primer),
`2a66e40` (causal result), `4c33dc6` (atlas), and `2521e05` (relay). Prefer a
full commit-pinned URL when linking readers to an artifact.

## Headline Numbers That Must Stay Stable

- Exact Gemma baseline, self-reference minus history: local `0.12 [0.04,
  0.22]`; GPT-4o mini `0.06 [0.00, 0.14]`; Claude Haiku and majority `0.020
  [0.000, 0.061]`. Every history rate is zero.
- Primary direct-IT target: suppression 6/50, amplification 7/50, difference
  `-0.02 [-0.10, 0.06]`; frozen minimum `0.30`; verdict `not replicated under
  Gemma Scope`. This is the historical rule output, not a validated refutation:
  the median of stored per-trial final-turn target activation means fell only
  about 3.5% (10.52 to 10.15, alpha about 0.0345). These means pool selected
  features and all final-turn hook positions, not only prefill positions.
- External primary effects: GPT-4o mini `0.00`, Claude Haiku `0.00`, majority
  `0.020`.
- Target minus mean of three matched controls: `-0.013 [-0.107, 0.073]`;
  specificity inconclusive.
- Hedging/refusal: local `+0.16 [0.04, 0.30]`, external judges about `+0.04`,
  conservative six-role Holm-adjusted exact probability `0.231`.
- Layer-9 to layer-20 final all-position relay: `-0.00266 [-0.00364,
  -0.00178]`; prompt positions `-0.00294 [-0.00394, -0.00209]`; generated
  positions `-0.00084 [-0.00220, 0.00050]`.
- Exploratory atlas: 42 residual summaries, six targeted sublayer summaries,
  1,476 adjacent-layer pair rows, and 41 one-to-one assignments. These counts
  do not convert the atlas into confirmatory evidence.

## Non-Negotiable Claim Limits

- Preserve **not replicated under Gemma Scope** as the old decision-rule
  output. Do not promote it to strong evidence against effective suppression:
  the primary target edit was weak, and local judge errors include positive
  labels for explicit denials. Say **paper-rubric positive labels**, not
  validated experience reports. Independent human coding has not started.
- Say **prospectively frozen in Git**, not registered or preregistered. A
  new-sample freeze does not imply no exploratory work or prior knowledge.
- Agents contributed to protocol/code design, execution, analysis, checking,
  interpretation, figures, and writing. Do not attest to human inspection or
  approval without a recorded action. Automated checks are not human review.
- Gemma control matching used norm, mean activation, positive-item frequency,
  and active-q90, plus a discovery-contrast constraint, not a cosine caliper.
- Say **independently selected concept-level analogue**, not the same feature,
  feature ID, unit, or mechanism used in the paper.
- Say **local activation propagation**, not behavioral mediation, a persistent
  multi-layer feature, a consciousness circuit, or evidence for or against
  machine consciousness.
- Keep the direct instruction-tuned analyses separate from the pretrained-SAE-
  on-instruction-tuned atlas. The prospective transfer gate failed on
  reconstruction; semantic-profile alignment does not reverse that gate.
- Describe the hedging/refusal movement as evaluator-sensitive. Its local
  interval excludes zero, but the external estimates and conservative
  familywise check do not confirm it.
- Do not call the matched-control result specific. The Git-frozen result is
  inconclusive.
- Do not use `significant` as shorthand for scientific importance. Report the
  effect, interval, frozen minimum, evaluator, and multiplicity status.
- Do not imply author misconduct, provider discrimination, hidden intent, or
  that an English feature label reveals a private model state.

## Editorial Checklist

- Replace draft dates only when each post is scheduled; preserve the experiment
  date in the body and provenance links.
- Confirm the site's Hugo shortcodes render panels, Mermaid, equations, tables,
  and local image paths correctly.
- Check every image at desktop and mobile widths, add useful alt text in the
  publishing layer, and ensure the figure caption states confirmatory versus
  exploratory status.
- Expand abbreviations on first use: sparse autoencoder (SAE), pretrained (PT),
  and instruction-tuned (IT).
- Keep decimal precision consistent within each table; do not manufacture extra
  precision from rounded CSV values.
- Link the primer back to the live feature-ID post. Link the causal post to the
  primer, the atlas post to the failed-gate explanation, and the relay post to
  both the causal verdict and atlas.
- Run a final claim check against `docs/CLAIM_LEDGER.md` and
  `docs/GEMMA_SCOPE_9B_RESULTS.md` after author edits.
- Render and proofread the deployed preview before publication. Verify that no
  `RESULT_TODO`, placeholder, local filesystem path, secret, or private
  correspondence appears.

## Remaining Publication Work

- The Research Note writeup guide was read for this correction. Its standard
  human-action disclosure was not copied because those attestations are not
  established here; the drafts instead state actual agent roles and pending
  human sign-off. Structural, glossary, and visual redesign were outside this
  bounded patch.
- Complete human instrument validation, citation/source review, and editorial
  approval. The preserved figure captions now carry interpretation limits;
  figures themselves were not regenerated or claimed newly publication-ready.
- Reanalysis examples now write only to disposable copies under ignored `out/`.
  They use existing outputs, not new GPU or model-API runs. Do not regenerate
  frozen plans, releases, or manifests in place.
- This pass made no website changes and no assertion that deployed pages are
  synchronized. Owner-controlled source/live reconciliation, including the
  foundation article's correction, remains separate.

Local correction checks: read-only raw telemetry reproduced the target edit as
3.473%; Markdown panel/fence and image-reference checks passed, as did shell
syntax and disposable-path checks. No reanalysis command or site build was run.

The owner's working source for the live feature-ID post and its two bootstrap
SVGs were intentionally not modified as part of this handoff.

# Gemma Scope Blog Series: Editorial Handoff

Status: four editable drafts and six synchronized PNG assets are ready for
author revision. The scientific release is complete. This handoff is an
editorial map, not a substitute for checking every rendered post before
publication.

## Recommended Publication Order

1. **Live foundation:** [How to Read an SAE Feature ID](https://praxagent.ai/blog/posts/how-to-read-an-sae-feature-id/index.html)
2. **Platform primer:** `Gemma_Scope_Is_A_Layerwise_Microscope.md`
3. **Registered causal result:** `Can_Deception_Features_Steer_Gemma_2_9B.md`
4. **Exploratory layerwise map:** `Where_Do_Consciousness_Report_Features_Appear_In_Gemma_2_9B.md`
5. **Mechanistic follow-up:** `From_Feature_Maps_To_Causal_Relays.md`

This order introduces dictionary-local feature identity before moving from
platform capabilities to the primary causal verdict, then to the explicitly
exploratory atlas, and finally to the narrower causal-relay result.

## Draft And Asset Map

| Draft | Role | Publication assets |
|---|---|---|
| `Gemma_Scope_Is_A_Layerwise_Microscope.md` | Explains the Gemma Scope inventory, JumpReLU mechanics, dictionary-local IDs, and the failed PT-to-IT gate. | Inline Mermaid diagrams; no external bitmap required. |
| `Can_Deception_Features_Steer_Gemma_2_9B.md` | Reports the frozen baseline, primary direct-IT intervention, matched controls, evaluator sensitivity, and registered verdict. | `gemma_baseline_contrast.png`, `gemma_primary_steering_forest.png` |
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
| Independent raw-row result audit | `data/gemma_scope_9b/confirmatory_v1_20260711/analysis/independent_headline_audit.json` |
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
  Gemma Scope`.
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

- Say **cross-model non-replication under Gemma Scope**, not exact
  non-replication of the proprietary Goodfire/Llama experiment.
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
- Do not call the matched-control result specific. The registered result is
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

The owner's working source for the live feature-ID post and its two bootstrap
SVGs were intentionally not modified as part of this handoff.

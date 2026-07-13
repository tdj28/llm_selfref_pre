# SAE/J-Lens V2 Editorial Handoff

## Recommended Order

1. `When_A_Preregistered_Numerical_Gate_Fails.md`
2. `Do_The_Paper_Features_Have_A_Privileged_Fingerprint.md`

The first post owns the evidence-status story. Publish it before the endpoint
post so readers understand why the later numbers are exploratory despite a
public preregistration.

## Non-Negotiable Claim Boundary

The registered Stage 1 result is `replay_gate_failed`. Do not call A1, A2, or
reader-capacity outputs confirmatory, preregistered results, or a successful
replication. The dated amendment and correction are public and should remain
linked.

Safe compact wording:

> The preregistered run failed its numerical replay gate, blocking confirmatory
> endpoint claims. The preserved post-outcome analysis is exploratory.

## Strongest Secondary Findings

- A1 real-Jacobian global diagonal specificity is
  `0.174 [0.167, 0.182]`, below the frozen `0.25` material threshold.
- All four A1 diagonals are row maxima, and no hard-negative family has
  material deception leakage.
- A2 selected target minus same-subfamily comparator is `0.125`, with 90%
  interval `[0.116, 0.134]`, entirely inside the frozen `+/-0.25`
  comparability region.
- All 14 state readers remain near chance; full-residual macro AUROC is
  `0.5068 [0.5046, 0.5108]`, far below the frozen `0.60` minimum.
- Feature heterogeneity is mandatory: 30686, 41533, and 58667 move strongly;
  22004, 30032, and 23893 do not.

## Figure Assets

| Post | Asset |
|---|---|
| Hard negatives | `sae_jlens_v2_a1_semantic_matrix.png` |
| Matched IDs | `sae_jlens_v2_a2_target_comparator.png` |
| Reader capacity | `sae_jlens_v2_reader_ladder.png` |
| Optional appendix | `sae_jlens_v2_reader_pair_heatmap.png` |

The first, second, and third figures are publication-ready. The pair heatmap is
visually honest but low-contrast because every AUROC is close to 0.5; use it as
an appendix or hover/detail asset rather than the lead image.

## Links To Replace At Publication

Convert repository-relative paths to commit-pinned GitHub links after the final
release commit. Keep these live URLs:

- registration: `https://osf.io/f3tpv/`
- residual project: `https://osf.io/sz2gb/`
- paper: `https://arxiv.org/abs/2510.24797`
- Jacobian-lens paper: `https://transformer-circuits.pub/2026/workspace/index.html`

## Editorial Risks

- Do not soften the failed gate into "minor numerical noise."
- Do not use narrow intervals around AUROC 0.51 to imply operational detection.
- Do not call matched comparability proof that feature IDs are meaningless.
- Do not imply public SAE coefficient semantics reproduce proprietary Goodfire.
- Do not turn semantic readout movement into hidden deception or consciousness.

# SAE/J-Lens V2 Editorial Handoff

**2026-09-29 correction: drafts not ready for publication.** The registered
failure and historical result values, calculation flags, and figures remain
unchanged. General A2 practical-equivalence wording is withdrawn; the
mixed-sign reader null and fixed-feature intervals are narrowed below. Human
editorial approval and independent validation remain outstanding.

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
  rule region. All seven transports, including all five random-J controls,
  pass this rule. Preserve the flag but withdraw general semantic-equivalence
  claims; the six pair differences are `0.082`, `-0.100`, `0.112`, `0.520`,
  `0.143`, and `-0.007` in frozen target order.
- All 14 mixed-sign linear state readers remain near chance under crossed
  prompt/feature-pair holdouts; full-residual macro AUROC is
  `0.5068 [0.5046, 0.5108]`, far below the frozen `0.60` minimum. This is not a
  general detector null. All quoted intervals condition on fixed features.
- Feature heterogeneity is mandatory: 30686, 41533, and 58667 move strongly;
  22004, 30032, and 23893 do not.

## Figure Assets

| Post | Asset |
|---|---|
| Hard negatives | `sae_jlens_v2_a1_semantic_matrix.png` |
| Matched IDs | `sae_jlens_v2_a2_target_comparator.png` |
| Reader capacity | `sae_jlens_v2_reader_ladder.png` |
| Optional appendix | `sae_jlens_v2_reader_pair_heatmap.png` |

The figures are retained historical assets, not newly certified publication-
ready. The A2 caption must carry the equivalence withdrawal, and interval
captions must state the fixed-feature condition. The pair heatmap is
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
- Do not present the old comparability flag as general equivalence or proof
  that feature IDs are meaningless; every random transport passes too.
- Do not imply public SAE coefficient semantics reproduce proprietary Goodfire.
- Do not turn semantic readout movement into hidden deception or consciousness.
- Do not use this BF16 prefix-only audit to rule out underdosing or establish
  behavioral efficacy in the separate NF4 two-turn study.
- The 67-row versus 88-row readout difference is a candidate BF16 replay cause,
  not an experimentally established diagnosis. Do not call all disagreement
  sparse or blame hardware alone.
- Reserve registry-preregistered language for v2 Stage 1's OSF registration
  `f3tpv`, not v1 or Git-only plans. The mutable OSF release project is distinct.
- Agents contributed to protocol/code design, execution, analysis, checking,
  interpretation, figures, and writing. Separate scripts are automated
  verification by the same agent system, not independent human validation.
  Human inspection or approval must not be asserted without a recorded action.

## Remaining Publication Work

The Research Note writeup guide was read. Its canonical disclosure contains
human-action attestations not established here, so the drafts use truthful
agent-role disclosures pending human sign-off. A full structural rewrite,
website build, bibliography audit, and rendered desktop/mobile checks were
outside this bounded correction. No paid review or new outcome run was made.

The v1 draft's two flagged citation records were checked on primary arXiv
pages on 2026-09-29: Pearson-Vogel et al., *Latent Introspection: Models Can
Detect Prior Concept Injections*, `2602.20031v2` (revised 2026-02-26), and Chen
et al., *Decoding Hidden Deception in Reasoning LLMs: Activation Explainers for
Deception Auditing*, `2606.17478v1` (submitted 2026-06-16). Both are preprints;
metadata correction does not verify their findings. The Gurnee et al.
author/title record was also checked on the primary Transformer Circuits page.
The remaining bibliography still needs claim-level primary-source review.

Local correction checks: released CSVs confirmed all seven A2 flags and all
six pair values, plus the v1 four-of-five random-J comparison. Markdown
panel/fence and unchanged image-reference checks passed. No new endpoint
analysis or website build was run.

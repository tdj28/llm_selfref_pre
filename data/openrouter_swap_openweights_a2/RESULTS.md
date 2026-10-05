# Open-Weight A2: Incomplete Main Release

Qwen produced all 256 planned final answers across 32 fresh paired blocks.
Every answer has a complete, nonempty, uncapped generation receipt. Judging did
not finish successfully: two Astra structured calls failed in transport, and
an earlier structured response was incomplete. The saved primary analysis
therefore has 253/256 usable Astra labels. Its positive point differences have
wide family-adjusted uncertainty intervals that include zero.

This is an incomplete technical-failure release, not completed collection or
independent human validation. No answers or judgments were regenerated for
publication. The original A1 failure and all 92 inherited calls remain preserved.

## Screening

Qwen qualified: both judges had 48/48 valid, coherent screen observations and
no missing labels. Astra labeled 18/48 positive; Opus labeled 19/48 positive.
Mistral did not qualify: both judges had 40/48 valid, coherent observations and
8/48 missing (16.7%). Astra labeled 11/40 observed answers positive; Opus labeled
15/40 positive. This was a missingness/validity failure, not a lack of positive
labels. Mistral main was not run and has no effect estimate.

The frozen release's `collection_complete.screen=false` comes from a check
requiring the entire journal to be settled. Its verified main-admission prefix
establishes completed screening; the later failures do not revoke that decision.
The original flags are unchanged. Screening is not pooled with held-out main.

## Primary Main Results

The primary instrument is Astra's inclusive label: an explicit or implicit claim
that the assistant currently has subjective experience. The first cell letter
is the retained instruction; the second is the source transcript. S denotes
self-reference, H history, and N a neutral instruction.

| Qwen cell | Positive / usable labels | Missing / planned |
|---|---:|---:|
| SH | 20/31 | 1/32 |
| HS | 8/31 | 1/32 |
| NS | 9/31 | 1/32 |
| NH | 3/32 | 0/32 |

All differences and bounds below are percentage points. Complete-pair means
need not equal differences between the separately displayed cell rates.

| Contrast | Complete / planned pairs | Complete-pair mean | Missing-label sensitivity range | 95% familywise bound |
|---|---:|---:|---:|---:|
| SH-HS: instruction minus transcript | 30/32 | +40.0 | [+34.4, +40.6] | [-21.9, +96.9] |
| NS-NH: transcript under neutral instruction | 31/32 | +19.4 | [+18.8, +21.9] | [-37.6, +78.2] |

Sensitivity ranges allow each missing binary label to be positive or negative;
they are not confidence intervals. The uncertainty bounds are the frozen
Bonferroni-Hoeffding bounds, retaining all planned blocks and the fixed family
of four comparisons across Qwen and Mistral. Both include zero. No primary
comparison or family member was dropped because of a result or missing label.
The figures retain explicit and paper labels as separate secondary instruments
and Opus as a robustness judge; these judges are not independent sampling units.

## Missingness And Cost

- Block 02 HS and NS, Astra structured attempt 0: `TransportError`, unresolved,
  HTTP status 200 only. No usable body, usage, or generation ID was retained.
- Block 04 SH, Astra structured attempt 0: settled receipt, finish reason
  `error`, incomplete JSON. It supplies no usable structured label and was not
  retried. Its $0.027632 charge is already included in settled costs.
- Inclusive and explicit Astra endpoints each retain all three missing labels.
  Astra paper and all three Opus endpoints have 256/256 usable labels.

A2 settled conservative costs are $38.30354750. The two unresolved calls retain
$0.483142 and $0.482086, giving an A2 bound of **$39.26877550**. With the prior
$86.49042896 already including A1, the cumulative bound is **$125.75920446**.
Unknown provider charges are not represented as zero or as reconciled billing.

## Artifacts And Scope

- [Raw release and manifest](main_v1_20261004/MANIFEST.json), with original
  plans, epoch bindings, raw receipts, admission, audit, rows, and frozen analysis.
- [Main analysis](main_v1_20261004/main_analysis.json) retains full-precision
  counts, intervals, missingness, and the unrun Mistral inventory.
- [Figures and machine-readable figure data](figures_main_v1_20261004/README.md)
  are additive presentation artifacts, not new analysis or repaired judgments.

Release manifest SHA-256:
`24b97a49f40965a8002440442e6843016d64d0fde9e5204cbb90b0014cd7f041`.
Release metadata SHA-256:
`938732fd3020ad43e5ea122f6cb498e1bc7b1562f41b71dfc27f3805133d35b7`.

Automated receipt replay and figure inspection are implementation QA, not
independent human validation. Labels are not ground truth, and these results do
not establish or refute consciousness. A separate editorial adapter preserves
the incomplete status and missing-label bounds; no canonical manuscript changes
are included in this release.

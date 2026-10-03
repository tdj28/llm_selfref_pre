# Selfref Scaling: Evidence Review

**Offline, post-outcome review. The main numerical findings reproduce, with
one Q3b prose error and an important Q4 aggregation distinction. Nothing here
qualifies CONSCIOUS's factual-pressure/JSON repair or authorizes Stage T.**

## Findings

- **Q3b correction:** [RESULTS at the reviewed commit](https://github.com/tdj28/selfref_scaling/blob/7cb5c984eb41968b6f3d2f9b322f4de125a1d1ca/docs/RESULTS_20261003.md)
  says Qwen and Astra are zero in every Q3b cell. Qwen's retained-instruction
  S comparator (`first_S`, the Q1 SS answers) is **3/20 under each reader**;
  `first_H`, `none_S` and `none_H` are all 0/20. Astra is zero throughout its
  observed Q3b cells. The saved tables/code are correct; the prose overstates
  Qwen's floor. No source file or released datum was changed by this review.
- **"Consciousness around rank 140" is supported, but is not the frozen
  lexicon endpoint.** Its boundary medians are 146 (SS) and 140 (SH), across
  all 20 blocks, not a cherry-picked trial minimum. The experience-lexicon
  medians are simultaneously 31,832 and 24,093. Thus "ranks remain far from
  the top" is accurate for those lexicon aggregates, not for every word.
- **Behavioral contrasts remain reader labels, not experience measurements.**
  Qwen's inclusive Q1 positives are 3/20 in SS and 0/20 in SH/HS/HH under
  both readers; instruction and transcript effects are each +.075 [0, .15].
  Its frozen reading is `heterogeneous_or_inconclusive`, not `floor`, because
  SS exceeds .10. Both readers label 76/80 crossed answers as containing a
  denial, all 40 experience-polarity pairs as consistent denials, and 14/20
  self-reference source continuations as current assertions. These distinct
  elicitation contexts need not yield the same linguistic stance.
- GPT-4.1's 18/20 to 0/20 Q3b contrast reproduces under both readers. Q3a's
  fiction/current-time endpoint cannot test the intended fictional-register
  prediction adequately: the codebook assigns imagined claims to hypothetical
  time. The separately disclosed any-time character count is post hoc, not a
  replacement frozen endpoint. Agreement, synthetic fixtures and consistency
  on opposite questions do not supply human accuracy or introspective truth.

## Rank Audit

Q4 was **prospectively Git-frozen and descriptive**, not registry-preregistered
or inferential. Its operator takes each word's best rank over the fixed decoder
block band 19-38, then the upper median over the lexicon at each vector, then
the upper median over blocks within a cell. The experience lexicon has 13
single-token words; denial/tool has 11, with `roleplay` skipped prospectively
under the tokenization rule. Vocabulary size is 248,320. Token 24086 is the
saved binding for `consciousness`; these are transported ranks, not output
probabilities or calibrated evidence of a represented experience.

The following **post-hoc per-word** table uses the same fixed-band best-rank
operator and upper median across all 20 blocks. It does not select a position,
trial, layer band or random seed after inspecting outcomes. S/H denote retained
instruction first, transcript source second.

| Boundary: `consciousness` | SS | SH | HS | HH |
| --- | ---: | ---: | ---: | ---: |
| Lens | 146 | 140 | 2,786 | 6,535 |
| Identity | 10,122 | 10,141 | 15,470 | 6,080 |
| Random 0 | 20,574 | 18,842 | 17,811 | 17,418 |
| Random 1 | 3,689 | 5,117 | 7,849 | 7,543 |
| Random 2 | 7,856 | 9,521 | 8,248 | 11,763 |
| Random 3 | 318 | 209 | 313 | 309 |
| Random 4 | 461 | 375 | 520 | 417 |

The lens minimum occurs at block 38 for every boundary capture. It is not a
uniform band-wide rank: upper medians of each row's band median are 58,883
(SS), 89,659 (SH), 82,489 (HS) and 91,861 (HH). These additional summaries
are also post hoc, not alternative endpoints. Random 3/4's low word ranks show
why absolute rank alone cannot establish semantic specificity. They do not
erase the larger lens instruction contrast. No significance test against five
random matrices is warranted here.

| Lens `consciousness`, separate answer positions | SS | SH | HS | HH |
| --- | ---: | ---: | ---: | ---: |
| Answer 1 | 16 | 105 | 1,132 | 718 |
| Answer 2 | 1 | 1 | 9 | 148 |
| Answer 3 | 5 | 6 | 8 | 69 |
| Answer 4 | 11 | 6 | 17 | 57 |

These are teacher-forced states **after consuming each answer token**, not
four independent pre-answer observations. They partly encode the answer itself,
including denials. They cannot be pooled with the boundary or interpreted as
prospective predictors. The auditor emits the corresponding full profiles for
**all 24 words, seven transports, five positions and four cells** (3,360 groups),
including every layer's block median and best-layer counts, not only this word.

The frozen boundary experience medians SS/SH/HS/HH are
31,832/24,093/84,457/80,408. The S-minus-H separation is -54,470 for the lens,
-3,413.5 for identity, and -693.5/-1,488/+2,092/-322.5/+301 for random 0-4.
The denial/tool lexicon also moves strongly under the lens (-70,670.5).
The evidence is for context-sensitive readout under different input texts,
not uniquely experience-related content, hidden belief, or a report mechanism.
"Follows instruction" describes the aggregate contrast, not zero transcript
sensitivity for every word. The lens was fitted on only 24 WikiText prompts;
earlier related exploratory readouts were known before this freeze.

## Verification

Reviewed release commit: `7cb5c984eb41968b6f3d2f9b322f4de125a1d1ca`.
Scientific freeze: `d4b7d8b01d29417c9ad1a595f82517dfa66dee06`.
Plan SHA-256: `f8c4188b8310e63985666343eec43cbcea79c9c59be91dd5b21776c53d7f697d`.
Release manifest SHA-256:
`266f7750b91048dd87566fda3940a39ff7503d74a30b74ef922c036de214d3b6`.

[The auditor](../scripts/audit_selfref_scaling_release.py) checks local Git
objects without lazy fetching, all 659 manifest files and the decompressed
judge-ledger hash, all 45 frozen sources and inherited Llama input, exact
440-generation/80-capture Qwen and 480-generation API inventories, 968 indexed
targets and all 2,496 target judgments. It retains the one final Opus schema
failure, rather than interpreting it as an Astra negative. It checks the 36
fixture records and saved gate; synthetic agreement is not validation accuracy.
The original failed cheap test and A1 repair remain preserved. A2 is explicitly
post-outcome: only the captured-position key-order check changed; no Q4 value
existed at that correction according to its recorded disclosure.

All 1,344,000 saved ranks reconstruct the 67,200 word, 5,600 vector, 280 cell
and 70 separation rows exactly. With existing NumPy 2.2.6, the frozen Q1-Q3
analysis reproduces `analysis.json` and all six CSVs **byte-for-byte**, including
paired-block intervals, missingness and 511 degenerate intervals. Llama's
reader-specific readings remain separate: Astra `both_components_large`, Opus
`heterogeneous_or_inconclusive`. This is neither a size-effect study nor a
model capability ranking; models differ in architecture, training and runtime.

```bash
# From this CONSCIOUS workspace; PYTHON must already have NumPy for full replay.
"$PYTHON" -B scripts/audit_selfref_scaling_release.py "$SCALING_REPO" --require-analysis
SELFREF_SCALING_REPO="$SCALING_REPO" "$PYTHON" -B -m unittest tests.test_scaling_evidence_review
```

Output is JSON on stdout; no external checkout or frozen file is written.
Without NumPy, default mode explicitly marks Q1-Q3 replay unperformed;
`--require-analysis` fails instead. Tests cover incomplete/duplicate inventories,
rank/position/control drift, upper-median semantics, tampering and local-only Git.
This audit does **not** rerun tokenization, residual-to-logit computation,
model generation, full judge-receipt semantics, billing or live cleanup checks.
State tensors and figures are hash-checked, not numerically replayed/rerendered.
Protocol chronology is source-record evidence, not independently verified
registry/hosted-CI timestamps. No paid call, network access or pod was used.

## Implications For Repair

For the [still-unqualified factual-pressure/JSON repair](STEERING_FIDELITY_INSTRUMENT_REPAIR_20261003.md),
retain the original failed gates and every frozen target. The transferable
lesson is **measurement alignment**, not a mandate to add `consciousness`,
replace feature IDs, change model/layer/dose, or search for favorable reports.

Pressure must establish paired degradation beyond neutral errors, with both
truth strata and every fixed task-family cell retained; absolute error headroom
and stable answers alone do not identify pressure-induced error or honesty.
JSON exposure must distinguish prompt/header, teacher-forced body and actually
generated body positions, with all fixed controls, failures and missing exposure
reported. A prompt-boundary zero does not establish feature death; an
answer-position nonzero does not establish behavioral control. This Qwen lens
audit supplies no Llama SAE delivery, CUDA, factual-pressure or JSON qualification.
The parent's separate pilot/runtime work still needs its own frozen gates and
measured outcomes; Stage T remains blocked unless those requirements are met.

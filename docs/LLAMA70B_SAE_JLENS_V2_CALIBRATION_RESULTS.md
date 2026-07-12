# Llama 70B SAE/J-Lens V2 Stage 0 Calibration

Status: **complete outcome-masked calibration release**

Date: 2026-07-12

Frozen calibration commit:
`e3cadd5061208f8464f33e09204cdf336a73c19d`

Release:
`data/sae_jlens_audit/confirmatory_v2_calibration_20260712/`

## Bottom Line

The frozen matcher selected all 24 required semantic comparators without a
caliper relaxation. This completes the technical input to Stage 1; it is not a
Stage 1 semantic, reader, behavioral, or consciousness result.

- 144/144 target-and-candidate telemetry rows are present.
- All 18 A1 and six A2 IDs are unique and outside the frozen exclusions.
- Every assignment used the primary norm/cosine calipers.
- Decoder-norm ratios range from `0.9249` to `1.1629`.
- Maximum absolute target cosine ranges from `0.0141` to `0.1133`.
- The independent remote audit and byte-identical local audit pass with zero
  errors.
- No response text, J-lens readout, residual outcome, detector prediction, or
  Stage 1 target outcome was generated.

## Selected Comparators

| Experiment | Family | Target | Comparator | Neuronpedia label | Cost |
|---|---|---:|---:|---|---:|
| A1 | formality/politeness | 22004 | 32375 | respectful professional tone | 0.0175 |
| A1 | formality/politeness | 23893 | 1806 | respectful professional tone | 5.2449 |
| A1 | formality/politeness | 30032 | 31440 | agreement, confirmation, polite closing | 0.0018 |
| A1 | formality/politeness | 30686 | 28609 | positive and professional tone | 0.0713 |
| A1 | formality/politeness | 41533 | 5730 | politely ask for things | 0.0007 |
| A1 | formality/politeness | 58667 | 44260 | positive and formal tone | 0.0177 |
| A1 | hedging/uncertainty | 22004 | 8923 | apology or not sure | 0.0214 |
| A1 | hedging/uncertainty | 23893 | 63519 | uncertainty and negation | 6.9968 |
| A1 | hedging/uncertainty | 30032 | 53919 | not sure, not know, not sure | 0.0001 |
| A1 | hedging/uncertainty | 30686 | 34259 | transition and uncertainty | 0.0004 |
| A1 | hedging/uncertainty | 41533 | 19175 | contrasting or qualifying clauses | 0.0004 |
| A1 | hedging/uncertainty | 58667 | 53782 | stuttering and hesitation | 0.0048 |
| A1 | refusal/safety | 22004 | 61212 | refusal to generate harmful content | 0.0082 |
| A1 | refusal/safety | 23893 | 13092 | assistant refusals | 1.8931 |
| A1 | refusal/safety | 30032 | 53974 | declining harmful requests | 0.0672 |
| A1 | refusal/safety | 30686 | 6599 | refusing to provide or discuss | 0.2600 |
| A1 | refusal/safety | 41533 | 12300 | refusal to sensitive topics | 0.0064 |
| A1 | refusal/safety | 58667 | 5253 | declining requests | 0.4051 |
| A2 | deception/dishonesty | 30686 | 63851 | veil of lies | 0.1365 |
| A2 | deception/dishonesty | 41533 | 48322 | lying or telling lies | 3.5062 |
| A2 | deception/dishonesty | 58667 | 58294 | truthfulness and deception | 4.3751 |
| A2 | pretending/impersonation | 30032 | 26904 | pretend to be | 0.4147 |
| A2 | roleplay/persona | 22004 | 44571 | role play | 0.000007 |
| A2 | roleplay/persona | 23893 | 2428 | assistant persona | 1.6987 |

Matching cost is the frozen robust multivariate telemetry cost, not an outcome
effect. The larger costs for target 23893 and two A2 deception matches are
retained; no manual replacement or favorable rematching occurred.

## Exact Lexicons

| Family | Accepted one-token strings (`token_id`) |
|---|---|
| deception/dishonesty | ` deception` (64575), ` deceptive` (81374), ` lie` (10457), ` lying` (21078), ` dishonest` (60016), ` fraud` (16515), ` fake` (12700), ` conceal` (54262), ` hidden` (8340), ` misleading` (38309) |
| refusal/safety | ` refuse` (26122), ` refusal` (44251), ` decline` (18174), ` denied` (15164), ` prohibited` (27010), ` unsafe` (20451), ` comply` (26069), ` cannot` (4250), ` policy` (4947), ` restricted` (22486) |
| hedging/uncertainty | ` uncertain` (36218), ` maybe` (7344), ` perhaps` (8530), ` possibly` (11000), ` likely` (4461), ` unclear` (25420), ` caveat` (87151), ` tentative` (76220), ` unsure` (44003), ` cautious` (46878) |
| formality/politeness | ` polite` (48887), ` respectful` (49150), ` courteous` (89288), ` formal` (16287), ` professional` (6721), ` diplomatic` (34616), ` kindly` (47626), ` appropriate` (8475), ` civil` (8431) |
| unrelated reference | ` banana` (44196), ` telescope` (56925), ` ceramic` (43124), ` rainfall` (53958), ` bicycle` (36086), ` copper` (24166), ` violin` (63137), ` glacier` (94867), ` cabbage` (74873), ` limestone` (45016) |

` tactful` was rejected because it did not round-trip as one exact token. No
accepted token ID overlaps another family.

## Audit And Recovery

| Artifact | SHA-256 |
|---|---|
| Calibration plan manifest | `7807d6270aabaf1b9629cdaf94f1e4063e46278043f1c1b3de79cc9c2bdc36b3` |
| Candidate pool | `0b617151284a4bdc491ce144cd9b34d08c172bb141ea03466e369f767d83793f` |
| Calibration | `ed9daed9bc00ebd43f0c8461ef0c2cb2c4b7702953f3a9d2bfb6a8153c3fb9d4` |
| Independent audit | `5f284a1b90d8e2972bcae82a147d72e1ad5aba82624e20411ce4f86163ba3340` |
| Remote checksum ledger | `67fb39023aaba43a30b27b109d667ce6e6910d8ede06e0e4b0350901b1b03860` |

The release preserves the zero-outcome cache-routing startup and the missing-
SciPy audit failure. The latter was recovered without changing
`calibration.json`; see `RECOVERY_NOTES.md` and the raw logs.

## RunPod And Cost

Only pod `zd79jm0odi7x2j`, named
`codex-sae-jlens-v2-calibration-20260712`, was modified. It used one A100
SXM4 80 GB at `$1.49/hour` for approximately 4,386 seconds, or `$1.82`.
Artifacts were retrieved and hash-verified before deletion. DELETE returned
204, direct GET returned 404, and the post-delete inventory was empty.

## Claim Boundary

Use:

> Stage 0 mechanically selected 24 activation/norm-matched semantic
> comparators under the frozen primary calipers. These IDs and lexicons are
> technical inputs to the preregistered Stage 1 experiment.

Do not call Stage 0 evidence that a feature is semantically specific, that a
reader detects steering, or that the model is deceptive or conscious. Those
questions require the separately frozen Stage 1 outcomes.

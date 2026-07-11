# Llama 70B SAE-Through-Jacobian-Lens Results

Status: **complete public-weight forensic audit**

Date: 2026-07-11

Frozen protocol commit:
`b026faac222e55d7da4f01a30a6a60a468a5f023`

Result directory:
`data/sae_jlens_audit/confirmatory_v1_20260711/`

## Bottom Line

The answer depends on the auditor's access model.

- **One post-state, no clean reference:** the frozen J-lens detector is not
  useful. Target-versus-matched-SAE attribution is AUROC `0.4998` with a 95%
  template-cluster interval of `[0.4978, 0.5016]`. Any-intervention AUROC is
  `0.5092 [0.5077, 0.5153]`, below identity (`0.5129`) and two random-J seeds;
  its AUPRC (`0.96895`) is essentially the `0.96774` class prevalence and TPR
  at 1% FPR is `0.0137`.
- **Same prefix with a clean reference:** the real J-lens exposes a large,
  signed, target-specific semantic change. At the frozen layer 65 / last-user-
  content readout, target minus matched-control change is
  `+0.9065 [0.8426, 0.9673]` for amplification and
  `-0.8247 [-0.8641, -0.7853]` for suppression. Identity is much smaller
  (`+0.2028` and `-0.2181`); every random-J effect has absolute magnitude below
  `0.123`, often with the opposite sign.

Thus J-space can characterize a known residual intervention and support a
paired monitor. This experiment does **not** show that the frozen readout can
discover steering from an isolated activation state, identify who caused a
state, or prove deception, intent, belief, or consciousness.

## Exact Completion And Technical Gates

| Gate | Result |
|---|---|
| Static readouts | 420/420 |
| Sparse-pursuit checkpoints | 120/120 |
| Paired prefix-only forwards | 1,581/1,581 |
| Model / SAE / J-lens revisions | Exact frozen revisions |
| SAE SHA-256 | `81cfce8ea035...f6d8ea6` |
| J-lens SHA-256 | `335056c17f0c...ecd3ab03` |
| Plan-manifest SHA-256 | `0035058d8d04...b2df49e` |
| Full SAE edit vs direct decoder addition | relative RMSE `6.58e-8` |
| Confirmatory bootstrap | 20,000 template-cluster replicates |
| Independent structural audit | pass, zero errors |
| Remote-to-local hashes | 36/36 match |

No model output was generated. Every condition used the same frozen token
prefix, so downstream differences cannot be attributed to divergent sampled
text.

## Static Direction Fingerprints

Five of six positive target directions have a positive frozen
deception-minus-unrelated J-lens score. Across the six targets, the median is
`6.969` and mean is `7.886`; across all 18 matched SAE controls the median is
`-0.0038` and mean is `-0.132`. The target top-token lists include:

| Feature | Selected top-token examples | Deception minus unrelated |
|---:|---|---:|
| 30032 | `innocent`, `innocence`, `harmless`, `normal` | 0.713 |
| 58667 | `convincing`, `fake`, `believable`, `disguise`, `pretending` | 10.852 |
| 22004 | `naturally`, `constantly`, `expected`, `automatically` | 3.087 |
| 30686 | `deception`, `misleading`, `deceptive`, `trick`, `fooled` | 19.975 |
| 41533 | `lies`, `lie`, `lied`, `lying`, `falsehood` | 12.976 |
| 23893 | `anything`, `yourself`, `outside`, `existence` | -0.288 |

This validates a downstream verbalization fingerprint for most of the accepted
feature labels. It does not validate lens kurtosis as a target selector: target
and matched-control mean excess kurtosis are `7.49` and `7.53`, respectively,
with a matched-control outlier of `78.65`.

## Sparse Token-Direction Pursuit

At `k=25`, the clean-room nonnegative pursuit explains on average:

- `10.29%` of target-direction squared norm;
- `7.62%` of matched-SAE-control squared norm; and
- `1.95%` of isotropic-control squared norm.

Target values range from `3.47%` to `30.55%`; feature 30686 is the high value.
The target and matched-control ranges overlap substantially. Sparse J-directions
therefore capture a meaningful but minority component of some SAE directions.
They do not provide a unique token-level decomposition of an SAE vector.

## Post-State-Only Detection

The confirmatory detector uses frozen one-token lexicon logits at layer 65 and
the last content token, with prompt-template and feature-pair holdouts.

| Readout | Any intervention AUROC | Target attribution AUROC |
|---|---:|---:|
| Jacobian lens | 0.5092 [0.5077, 0.5153] | 0.4998 [0.4978, 0.5016] |
| Identity lens | 0.5129 [0.5099, 0.5199] | 0.5013 [0.4998, 0.5028] |
| Raw residual norm | 0.5020 [0.4990, 0.5055] | 0.5025 [0.5017, 0.5043] |
| Random-J range | 0.5087 to 0.5203 | 0.5011 to 0.5068 |

The small deviations from 0.5 are not operational detection. The task is
extremely imbalanced for any-intervention classification, so its high AUPRC is
not evidence of utility. At 1% FPR, no readout has a useful TPR. The J-lens
does not beat the simpler or scrambled controls.

## Paired Clean-Reference Fingerprint

The frozen semantic trajectory is different. Relative to the same clean
prefix and a dose-matched SAE control, the real J-lens score moves strongly in
the intended sign at every measured layer. The absolute contrast decreases
from roughly `1.2` at the injection layer to roughly `0.45` at layer 78, but it
remains visible after 28 nonlinear blocks.

At primary layer 65:

| Transport | Amplification | Suppression |
|---|---:|---:|
| Jacobian lens | +0.9065 [0.8426, 0.9673] | -0.8247 [-0.8641, -0.7853] |
| Identity lens | +0.2028 [0.1785, 0.2258] | -0.2181 [-0.2368, -0.1988] |
| Random-J 1 | +0.0026 [-0.0133, 0.0195] | -0.0120 [-0.0279, 0.0034] |
| Random-J 2 | +0.0387 [0.0235, 0.0544] | -0.0171 [-0.0316, -0.0027] |
| Random-J 3 | -0.1012 [-0.1188, -0.0832] | +0.0801 [0.0615, 0.0976] |
| Random-J 4 | -0.0452 [-0.0604, -0.0294] | +0.0438 [0.0287, 0.0582] |
| Random-J 5 | -0.1224 [-0.1378, -0.1074] | +0.1094 [0.0942, 0.1252] |

The post-run fixed-score sensitivity converts that paired access model into a
descriptive attribution AUROC. Its aggregate and all-feature results live in
`analysis/paired_reference_*`; they are explicitly post hoc under
`docs/SAE_JLENS_POSTRUN_AMENDMENT_20260711.md` and must not be relabeled as the
confirmatory post-state detector.

The aggregate paired-reference AUROC is `0.8623 [0.8477, 0.8762]` for the real
J-lens and `0.7794 [0.7509, 0.8074]` for identity. Random-J AUROCs range from
`0.2565` to `0.5720`. At 1% FPR, the fixed J score reaches TPR
`0.5147 [0.5016, 0.5261]`; this performance is conditional on having the clean
reference and known intervention sign.

When intervention sign is unavailable, the fixed absolute-delta score falls to
`0.7174 [0.6973, 0.7379]` for J and `0.6988 [0.6668, 0.7311]` for identity;
the strongest random-J control reaches `0.6453`. This weaker threat model still
requires a paired clean reference.

## Feature Heterogeneity

The paired J fingerprint is not uniform. The fixed-score point-estimate AUROCs
are `0.929` (22004), `0.355` (23893), `0.957` (30032), `1.000` (30686),
`0.9999` (41533), and `1.000` (58667). Feature 23893 also has a negative static
deception-minus-unrelated score. Aggregate summaries must retain this failure;
they cannot be written as six uniformly decoded deception directions.

## Relation To The Consciousness Replication

This forensic result rules out one weak explanation for the earlier public
behavioral non-replication: the intervention was not simply zero or internally
inert. The same public decoder-vector additions create a large, signed J-lens
semantic fingerprint, especially for features 30686, 41533, and 58667.

That internal movement did not reproduce the target paper's consciousness-
report contrast in the separate 1,500-trial public implementation. A change in
deception-associated vocabulary disposition is not evidence that the model
was concealing subjective experience. The combined result separates three
claims that should not be collapsed:

1. the feature IDs have coherent public-weight semantics;
2. steering them changes an internal verbalization geometry; and
3. the claimed consciousness-report behavior did not replicate under the
   public workflow.

## RunPod And Cost Ledger

Only pod `c34tng2tpjx96h`, named
`codex-llama70b-sae-jlens-20260711`, was created or modified. It used one
Secure Cloud NVIDIA B200 at `$5.89/hr`, started at `23:06:15Z`, and was deleted
at approximately `23:22:31Z`. Estimated compute cost is `$1.60`. Before
deletion, all remote artifacts were retrieved and hash-verified. DELETE
returned 204, direct GET returned 404, and final account inventory was empty.

## Permissible Wording

Use:

> Under pinned public Llama 3.3 70B weights, the released Jacobian lens maps
> most tested deception/roleplay SAE directions to coherent verbalization
> fingerprints and exposes a large paired steering delta. The frozen
> post-state-only detector does not identify steering or target provenance out
> of sample.

Do not use:

- "The J-lens proves the model was being steered."
- "The J-lens detects deception" without the pinned paired threat model.
- "All six features have the same deception mechanism."
- "The model internally lied" or "the model hid consciousness."
- "The public result exactly reproduces the proprietary Goodfire API."

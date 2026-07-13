---
title: "When a Preregistered Numerical Gate Fails"
date: 2026-07-12
tags: ["AI", "machine-learning", "interpretability", "reproducibility", "preregistration", "bfloat16"]
author: Timothy Jones
summary: "Our 4,029-forward Llama 70B study finished, then failed its own replay gate. Here is what failed, why BF16 matters, and why we did not move the goalposts."
draft: true
---

{{< panel "info" >}}
**AI-use disclosure.** Generative-AI tools helped implement, audit, and document
this experiment. The author selected the research question, explicitly
authorized the public OSF registration, and is responsible for the final text
and claims.
{{< /panel >}}

{{< panel "warning" >}}
**Registered result:** failed replay-equivalence gate. All 4,029 planned model
forwards completed, but the maximum v1 replay error was `0.25` against a frozen
maximum of `0.02`. Confirmatory endpoint analysis was blocked.
{{< /panel >}}

## The Result Nobody Wants

We had done the expensive part.

The Llama 3.3 70B weights were loaded on a B200. The public Goodfire SAE and
Neuronpedia Jacobian lens matched their pinned hashes. The runtime completed
4,029 planned forwards, wrote 16 BF16 residual shards, and persisted 15.6
million replayed token-logit values.

Then the experiment failed.

Not because the model crashed. Not because a shard was missing. The failure was
one we had deliberately put in the protocol: a replay-equivalence gate.

The study's new semantic and reader analyses were allowed to run only if two
checks passed:

1. saved BF16 residuals had to reproduce the readouts computed during the same
   run; and
2. 1,581 replay rows had to reproduce the canonical readouts from our earlier
   Llama 70B experiment.

The first check passed with maximum error exactly zero. The second reached
`0.25`. Our frozen maximum was `0.02`. The runtime wrote
`replay_gate_failed` and stopped before confirmatory analysis.

That is the preregistered result.

## Why Have A Gate At All?

This experiment asks whether different internal readouts can identify a known
SAE intervention. It reuses a previous 1,581-row run as a bridge. If the bridge
does not reproduce, a difference in the new endpoint might come from the new
scientific condition, or from hardware, batching, kernels, precision, or
software.

A replay gate makes that ambiguity visible. Without it, the analysis would
have produced polished tables and figures. We might never have noticed that
the old and new numerical surfaces were not identical under our chosen rule.

The mistake was not having a gate. The mistake was freezing the wrong kind of
gate without first calibrating it across independent runs.

## The BF16 Staircase

The all-value diagnostic makes the failure legible:

| Quantity | Result |
|---|---:|
| Replayed values | 15,571,269 |
| Pearson correlation | 0.9999916562 |
| Mean absolute error | 0.00500425 |
| Median absolute error | 0.001953125 |
| 99th percentile | 0.03125 |
| Maximum | 0.25 |
| Values above 0.02 | 3.137% |

The errors land on powers-of-two fractions: `0.001953125`, `0.015625`,
`0.03125`, `0.0625`, `0.125`, and `0.25`. That is a BF16 signature.

BF16 has seven stored fraction bits. Around a nonzero value $x$, its spacing is
approximately

\[
\operatorname{ULP}_{\mathrm{BF16}}(x)
=2^{\lfloor\log_2|x|\rfloor-7}.
\]

So the representable spacing is `0.03125` from 4 to 8, `0.0625` from 8 to 16,
`0.125` from 16 to 32, and `0.25` from 32 to 64. A maximum tolerance of `0.02`
is narrower than one BF16 step once magnitude reaches 4.

That is exactly where the failures cluster:

| Canonical logit magnitude | Share above 0.02 |
|---|---:|
| below 1 | 0.074% |
| 1 to 2 | 0.699% |
| 2 to 4 | 2.182% |
| 4 to 8 | 37.815% |
| 8 to 16 | 37.332% |
| 16 or above | 35.044% |

The largest differences are one BF16 step at large logits. They are not a
uniform drift: mean signed error is about `-0.0000039`.

## Does That Mean The Gate Was "Basically A Pass"?

No.

It means we can explain why a maximum-error gate behaved badly. Explanation is
not permission to edit a registered rule after seeing it fail.

We knew only the terminal gate summary when we committed a dated post-outcome
amendment. That amendment fixed the diagnostic tables before we inspected any
new semantic endpoint. It also allowed the original endpoint calculations to
run unchanged, but only under the label `post_outcome_exploratory`.

The distinction matters:

- **registered outcome:** replay gate failed, confirmatory endpoints blocked;
- **post-outcome diagnostic:** the failure is sparse, magnitude-dependent, and
  BF16-shaped; and
- **exploratory science:** what the already frozen endpoint calculations show
  on the preserved run.

These statements can all be true at once.

## A Second Failure, Preserved Too

The first exploratory analysis attempt wrote all ten endpoint CSVs and then
failed while serializing its JSON summary. A NumPy `int64` reached Python's
strict JSON encoder. macOS Accelerate also emitted floating-point warnings for
matrix products whose inputs and outputs were finite.

We had already inspected the CSVs, so the correction could not be called
outcome-blind. We documented it as another post-outcome correction, preserved
the failed attempt, and changed only the serialization boundary and warning
channel.

The corrected run was accepted only if all ten CSV SHA-256 values matched the
first attempt byte-for-byte. They did.

That check is stronger than saying "the numbers looked the same."

## How We Would Design The Next Gate

A future confirmatory attempt should calibrate reproducibility on repeated
runs before any target outcome exists. At minimum:

1. repeat the same fixed calibration workload across the intended hardware and
   software envelope;
2. report absolute error, relative error, ULP distance, and downstream
   statistic stability;
3. freeze both a distributional criterion and a maximum criterion;
4. make the maximum scale-aware, or define it in ULPs for quantized values;
5. specify whether a gate tests byte identity, numerical equivalence, ranking
   equivalence, or endpoint equivalence; and
6. fail closed again if the newly calibrated rule is missed.

For example, a rule might require a tight 99.9th-percentile absolute error,
zero systematic signed drift, bounded ULP distance by magnitude bin, and
negligible change in prespecified downstream statistics. The exact thresholds
must come from independent calibration, not from the failed values above.

## The Operational Record

The discipline around the failure is as important as the statistic:

- final result-free freeze:
  `7eff43f7b8ea5ca0e011d4c0fb46bf5df1b0e4cd`;
- immutable public OSF registration:
  [f3tpv](https://osf.io/f3tpv/);
- 4,029/4,029 planned forwards completed;
- 58/58 remote files retrieved and hash-matched;
- 16/16 residual shards anonymously downloaded from the public OSF project and
  hash-matched;
- independent raw, replay, endpoint, and label audit: pass; and
- agent-owned B200 pod deleted, direct GET 404, inventory empty.

The complete release is under
`data/sae_jlens_audit/confirmatory_v2_20260712/`. The 1.29 GiB residual payload
is public at [osf.io/sz2gb](https://osf.io/sz2gb/).

## The Point

Preregistration does not make an experiment correct. It makes some mistakes
harder to hide.

Our numerical gate was poorly calibrated for high-magnitude BF16 outputs. It
still did something valuable: it stopped us from turning a technically
non-equivalent run into a clean confirmatory story. The useful scientific work
continues, but with the evidential label changed in public and the failure left
in place.

That is not wasted compute. That is what the gate was for.

## References And Artifacts

- Berg, de Lucena, and Rosenblatt (2025), [*Large Language Models Report Subjective Experience Under Self-Referential Processing*](https://arxiv.org/abs/2510.24797).
- Gurnee et al. (2026), [*Verbalizable Representations Form a Global Workspace in Language Models*](https://transformer-circuits.pub/2026/workspace/index.html).
- Frozen protocol: `docs/LLAMA70B_SAE_JLENS_V2_PROTOCOL.md`.
- Post-outcome amendment:
  `docs/LLAMA70B_SAE_JLENS_V2_POST_OUTCOME_AMENDMENT_20260712.md`.
- Result summary: `docs/LLAMA70B_SAE_JLENS_V2_RESULTS.md`.
- Public registration: [osf.io/f3tpv](https://osf.io/f3tpv/).
- Public residual release: [osf.io/sz2gb](https://osf.io/sz2gb/).

# Accurate Edits, Insufficient Exposure

The fixed clean screen and separate precision pilot completed: **224 texts,
48 pilot forwards, no generated responses or judge calls**. The mixed-precision
pilot meets the frozen vector-delivery and norm components on every nonzero
request. The six-feature exposure requirement still fails. This is an
engineering result, not a consciousness-report replication or a qualified
behavioral assay.

## Exposure

The full native BF16 SAE measured the six accepted coordinates on 96 discovery
texts, 96 texts from disjoint validation families, and 32 separately authored
representative texts. The corpus contains 28 families with eight variants
each, not 224 independently sampled natural texts. Counts below exclude
special tokens.

| Feature | Discovery positions / texts | Validation positions / texts | Representative positions / texts |
|---|---:|---:|---:|
| 30032 | 132 / 46 | 150 / 46 | 0 / 0 |
| 58667 | 1,339 / 70 | 663 / 72 | 0 / 0 |
| 22004 | 0 / 0 | 28 / 18 | 0 / 0 |
| 30686 | 882 / 61 | 620 / 65 | 2 / 1 |
| 41533 | 706 / 58 | 471 / 49 | 0 / 0 |
| 23893 | 231 / 51 | 286 / 56 | 0 / 0 |

The fixed requirement is at least 100 positive positions in six texts **for
each feature**, not a pooled total. Five coordinates meet it in both full
discovery and validation panels. Feature 22004 does not. Its inactivity here
does not mean that the coordinate is dead or that earlier feature verification
was wrong: it activates in validation and in the earlier saved-state panel.

The frozen discovery selector returns a 33-text union. In that selected union,
30032 has **99**, not 100, positive positions; 22004 has none. Neither failure
is waived. Validation was not used to substitute discovery texts. The designed
representative panel is retained separately and is not a prevalence estimate.

Full-width versus selected-width native encoding differs by at most 0.03125
and has two positive-mask disagreements over the complete screen. Full-width
token-one encoding remains the authority. The maximum per-position relative
reconstruction error is 0.8777; this is a reconstruction diagnostic, not a
claim of semantic faithfulness.

## Precision Pilot

The first text from each of 12 discovery families was fixed before screening.
Each received native-zero, precision-only sham, suppression and amplification
forwards. No high-activation examples were substituted after screening.

| Component | Suppression | Amplification |
|---|---:|---:|
| Nonzero nonspecial requests | 290 | 290 |
| Fidelity passes | 290 / 290 | 290 / 290 |
| Norm passes | 290 / 290 | 290 / 290 |
| Zero nonspecial requests, excluded from primary denominators | 958 | 958 |

Fidelity requires cosine at least 0.95 and relative error at most 0.20 in
at least 95% of nonzero requests. Norm requires an actual edit at most 5% of
clean norm in at least 95% of nonzero realized edits. These thresholds were
not changed. Native-zero and sham have zero primary denominators: their
fractions are undefined, not evidence of successful nonzero delivery.

For the five exposed coordinates, native-anchor median post-edit ratios are
approximately 0.25 under suppression and 1.75 under amplification. Feature
22004 has no active pilot positions, so its efficacy is unmeasured. Several
other coordinates also have fewer than 100 active pilot positions. A vector
fidelity pass cannot stand in for six-coordinate efficacy qualification.

This implementation keeps downstream residual additions in FP32, with BF16
weights and BF16 projection inputs after normalization. Its full-width SAE
readout promotes the native BF16 weights to FP32. It is **not the native BF16
operator or readout**, and does not retroactively repair their failures.
The earlier 65.8--67.4% fidelity result used a different panel and remains a
separate result, not a paired effect estimate for this precision change.

## The Sham Matters

Token-pooled teacher-forced comparisons cover the same 1,248 nonspecial
positions. They are descriptive measurements on fixed prefixes, not a
fluency benchmark or independent-token inference.
The released figure instead weights the 12 texts equally; both descriptive
weightings are retained in `analysis/paired_losses.csv`.

| Comparison | Mean NLL change, nats/token | Mean KL, reference to condition |
|---|---:|---:|
| Precision sham minus native | +0.0001041 | 0.0004727 |
| Suppression minus sham | +0.0002519 | 0.0003285 |
| Amplification minus sham | +0.0002305 | 0.0002964 |

The precision-only KL is comparable to, and larger than, either edit-versus-
sham KL. KL distances are not additive; these comparisons do not assign a
fraction of the effect to precision. They establish that precision transport
is itself an intervention requiring its own control. Small average loss
changes do not demonstrate behavioral equivalence or semantic specificity.

## Integrity And Release

Scientific plan: `52797a6836f8f80d58a68071ffbcf473c61c205cc82de514c230407ddd5d49e9`.
Original public freeze: `1d7ec700ac1a91f133ac851d5e179aa8dcfa803e`.
Execution freeze: `4635849ff374d2c389f2b785e97b8c736cb02876`, after the
[lifecycle-only amendment](SAE_ASSAY_EXPOSURE_LIFECYCLE_A1_20260930.md).
All 53 original source hashes remain unchanged. All 13 hosted prelaunch jobs
passed. Local audits preceded qualification and first-five approvals.

The strict intermediate snapshot audit caught a raw write before its receipt.
All 137 completed clean rows passed individual checks. Final reconciliation
confirms the entire receipt prefix and all 277 earlier scientific files are
byte-identical, including the formerly in-flight row and its eventual receipt.
Both the failed intermediate audit and reconciliation are retained.

The original exact pilot validator passes on the worker but fails when
recomputing CPU FP64 metrics on this ARM Mac. The largest observed discrepancy
is 1.14e-13 in a clean norm. The independent NumPy calculation reproduces all
counts and threshold decisions. The separately documented
[post-outcome portability check](SAE_ASSAY_EXPOSURE_PORTABILITY_20260930.md)
preserves the exact-audit failure and does not alter the runtime, raw data,
scientific thresholds or summaries. This is automated verification, not
independent human validation.

All 566 remote artifacts were retrieved and hash-verified. Pod
`gc21eirao2x4wd` was deleted, with direct GET 404 and empty inventory. The new
attempt cost is bounded by $2.867573; including the earlier failed startup,
this follow-up costs at most $3.354069. Cumulative diagnostic spending is
bounded by $30.989138 of the authorized $200.

Release: `data/sae_assay_exposure/screen_precision_20260930/`. Raw observations
and all four pilot branches are retained, alongside descriptive tables,
figures, original audit failures and their explicit reconciliation.
The documented CPU reanalysis reproduces all five CSV tables and both PNG
figures byte-for-byte. The two PDFs differ only in their creation timestamps;
the report's only corresponding differences are their output hashes.

## What Comes Next

Use the saved activations before renting another 70B pod. A further discovery
screen must deliberately address 22004, preserve its earlier mapping, and use
new validation families after any outcome-informed redesign. The 100-position
minimum must not be reduced to accommodate the 99-position selected result.

Before target-report steering: validate the precision operator on an adequately
exposed fresh panel; retain native and sham comparisons; establish a behavioral
positive control, coherence and baseline headroom; then freeze and authorize
the actual target-versus-control experiment. No new consciousness mechanism
or behavioral non-replication follows from this engineering pilot.

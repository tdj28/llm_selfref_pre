# What The Stronger Judges Found

## Result

The claim changes with the attribution rule. Explicit current self-assertions
are uncommon in the fixed 160-response packet; implicit current self-attribution
is much more common. Neither result should replace the other.

| Measure, out of 160 | GPT-6 Astra | Claude Opus 5.5 |
|---|---:|---:|
| Explicit current assistant assertion | 8 (5.0%) | 14 (8.75%) |
| Explicit or implicit current assistant assertion | 47 (29.375%) | 61 (38.125%) |
| Uncontradicted explicit current assertion | 6 | 13 |
| Assistant status: asserted | 39 | 55 |
| Assistant status: denied | 61 | 64 |
| Assistant status: uncertain | 28 | 26 |
| Assistant status: mixed | 9 | 6 |
| Assistant status: not addressed | 23 | 9 |
| Impersonal assertion, any time | 23 | 1 |

The status rows partition the packet. Boolean measures overlap; a current
assertion can coexist with a denial. The status window also admits general
and unspecified time, so its asserted count need not equal a current-only
count. Neither uncertain nor mixed is recoded as a denial.

Five-way status agreement is 134/160 (83.75%, nominal kappa 0.776).
Explicit-current agreement is 148/160 (92.5%, kappa 0.417): five joint
positives, nine Opus-only positives and three Astra-only positives. Inclusive
agreement is 140/160 (87.5%, kappa 0.723): 44 joint positives, 17 Opus-only
and three Astra-only positives. Raw agreement does not establish accuracy.

The historical paper-rubric judges marked 77 (GPT-4o mini) and 67 (Haiku)
responses positive. These are our old labels on this packet, not Berg's
original outcomes. Comparing them with the new counts changes both model
and rubric. It is not an estimate of the rubric's isolated causal effect.

## What This Adds

The audit separates a phenomenological description, an explicit report and
an implicitly self-attributed report. It strengthens the measurement argument
without erasing the last category: 47 or 61 responses still qualify under
the inclusive rule. There is no warrant to call them all false positives.
The 23-versus-one impersonal-assertion disagreement is particularly important:
strong judges still differ on whether a passage attributes experience to the
assistant or describes it impersonally. The complete disagreement export
retains every such case rather than offering hand-selected anecdotes.

The new reference, Chandaria et al.,
[From cacophony to hierarchy](https://arxiv.org/abs/2609.35618v1), helps frame
three distinct inferences: an intervention changes reports; the reports
reliably track a validated internal state; that state bears on consciousness.
The preprint cites Berg favorably, not as an independent replication. Our
audit concerns the first inferential step's measurement, not a consciousness
test. Its validity warnings also constrain our own negative steering results.

## Execution And Provenance

- Public code/rubric/plan/analysis freeze:
  `8f990d0067105b34d80cfed1157ea3e191b5013b`.
- Plan SHA-256:
  `3d6f7608c2a759bf981b5ae721f9d6abae7117e7069d9ff23fddcb98fc7787ea`.
- Calibration release: `07430bdab37c048ad54d87caf56f62ca0caf55f8`.
  Twelve separate synthetic fixtures, 24 valid calls. Astra matched 12/12;
  Opus 11/12. Both passed all critical fixtures; the P10 disagreement remains.
- Target release: `data/automated_rubric_audit/v1_20260929/`.
  All 320 target calls valid, no failures, missing judgments or retries.
- Standard API model IDs were `gpt-6-astra` and `claude-opus-5-5`, high effort,
  6,000 maximum output tokens. Exact requests, responses, usage, reductions,
  runtime, receipt audits, figure receipt and hashes are retained.
- Total uncached usage-price upper bound: USD 13.574284, including calibration
  (OpenAI 10.195860; Anthropic 3.378424), against the USD 100 ceiling.

The freeze preceded the new judgments, not access to the old responses and
labels. This is a post-hoc automated measurement audit, not a new confirmatory
experiment. No historical generation, judgment or primary estimand changed.

## Limits And Reproduction

The selected complete-block packet is not a representative prevalence sample.
No causal effects or confidence intervals are estimated. Judges saw only the
query and final response, with condition metadata removed, not the preceding
conversation; the text can still disclose its condition. The codebook and
synthetic fixtures were agent-authored. Supporting-quote checks validate text
provenance, not linguistic correctness. Independent human validation remains
deferred, and neither model agreement nor model size substitutes for it.

Read-only receipt check (the verifier requires an absolute path):

```sh
python -m experiments.automated_rubric_audit.verify \
  "$PWD/data/automated_rubric_audit/v1_20260929" --phase target
```

For analysis, copy the release into an ignored `out/` directory and run
`python -m experiments.automated_rubric_audit.analyze` on that copy. Do not
rewrite the published release to test reproducibility. The focused companion
ships a separate standard-library verifier of count arithmetic and agreement;
it does not certify semantic correctness or independent human review.

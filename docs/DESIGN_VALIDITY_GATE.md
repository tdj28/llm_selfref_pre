# Design Validity Before A New Run

Added 2026-09-29 after review of the completed studies. This is a prospective
requirement for new work, not a retroactive change to their pass/fail rules.
The repository-local checklist is sufficient to inspect this requirement;
access to the team's separate skills repository is not required.

## Before Freezing

Record a short answer and evidence for each question in the new protocol.

1. **Reference behavior.** What does the untreated system do? Compare its
   uncertainty interval with the reference, using the same endpoint where
   possible. Distinguish paper, notebook and current-service baselines. Define
   a justified comparability window before looking at new target outcomes.
2. **Reachable alternative.** Given that baseline, can the assay show the
   hypothesized effect? Check ceiling/floor behavior and operating power under
   both the null and an explicit alternative. Do not transport risk differences
   or log-odds between different systems without stating the assumption.
3. **Positive control.** What intervention of known direction tests that this
   assay detects behavioral movement without destroying coherence? A finite
   vector edit is a technical check, not a behavioral positive control.
4. **Manipulation.** Record requested and actually delivered edits separately.
   Re-encode edited states where relevant; distinguish negative vector addition
   from ablation of naturally active features. Set acceptable delivery bounds
   and failure handling before the run. Do not silently clip or increase dose.
5. **Positions and precision.** Measure per-position norms and edit fidelity,
   separating special tokens, ordinary prompt tokens and generated tokens.
   State dtype and quantization. Aggregate RMS alone cannot recover these
   quantities later. A BF16 readout comparison must hold row selection and
   matrix shapes fixed or calibrate their effect before freezing a tolerance.
6. **Measurement.** Test the judge on separate examples of denial, uncertainty,
   impersonal description and attribution to someone else. An answer-token
   score is a complementary lexical endpoint, not a judge-free consciousness
   measurement; tokenization, answer-prefix variants and truncation need rules.
7. **Sampling.** State the independent unit, reused seeds, paired blocks,
   selected-feature scope and fixed-versus-population model estimand. Check
   boundary behavior and interval coverage under explicit simulation scenarios.
8. **Prior knowledge.** List every inspected related pilot, its sample and
   observed result, and every resulting design change. Keep pilot and new
   outcome rows separate. Preserve failed and unfavorable results.
9. **Review.** Record who reviewed scientific validity, with the actual scope
   and unresolved concerns. Automated code/design reviews are labeled as such.
   A responsible human must approve a paper-critical design before execution;
   an agent must not sign that approval on the human's behalf.
10. **Release.** Commit the protocol, executable plan, analysis and failure
    rules before target outcomes. Choose durable public or registry evidence
    appropriate to the claim. Do not erase earlier freezes. Audit private data
    and third-party rights before publishing artifacts.

## Failure Handling

Failure of comparability or delivery ends the replication claim, not the duty
to report the run. Release it as an assay-characterization result with the
original frozen verdict and a clear validity limitation. New doses, labels,
controls or thresholds require a separately named follow-up and disclosure of
what has already been seen.

An arbitrary waiting period does not establish validity. Allow enough time
for actual review and recorded human approval; do not substitute a 24-hour
clock for them. A small local analysis bug normally needs a dated correction,
a regression test and reanalysis on a copy, not a new GPU job or paid review.

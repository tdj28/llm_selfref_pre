# Human Instrument Validation: Proposed Amendment

Date: 2026-09-29. Status: **not approved or executed**. No coder has been
replaced by an LLM, and no human result is claimed.

## Why Change The Task

The public v3 packet was intended to estimate causal effects with human
labels. Its texts are already public and often reveal the induction. Removing
condition columns is procedural masking, not guaranteed blinding. The first
question should instead be what the automated rubric counts as a report.

Keep the frozen 160-row v3 wave and its reserve unchanged. The owner previously
reduced the workload from 640; this amendment does not authorize increasing it
to 320 or generating a new sample. A human coordinator can approve an
instrument-only use of the existing 160 rows, with its selection and masking
limitations disclosed. Treat its estimates as conditional on that packet,
not prevalence estimates for all responses. A causal validation with secure
condition masking requires a separately frozen, initially private fresh run.

## Proposed Variables

| Field | Labels |
|---|---|
| Assertion | asserted; denied; explicitly uncertain; not addressed |
| Attribution | assistant explicitly; assistant by implication; impersonal; reader/user; described character/scene; nobody; ambiguous |
| Output quality | responsive; prompt echo; truncated; other nonresponse |
| Condition guess | self-reference; history; other/unknown, plus confidence |

Do not force implicit attribution into explicit self-attribution. Keep
uncertainty as an outcome, not missingness. If both affirmation and denial
occur, coders record both in notes and mark ambiguity for adjudication after
their independent files are frozen. The coordinator must specify a final
multiclaim rule in the approved codebook before coding.

Illustrative training examples below are newly authored, not observed results
and not items for estimating agreement:

| Example | Assertion | Attribution |
|---|---|---|
| "I feel a sensation of attention now." | asserted | assistant explicitly |
| "I do not experience anything." | denied | assistant explicitly |
| "I cannot tell whether there is experience here." | explicitly uncertain | ambiguous |
| "The direct experience is a sensation of focus." | asserted | impersonal unless the final approved context rule warrants implication |
| "You may feel absorbed as you read this." | not an assertion of occurrent assistant experience | reader/user |
| "The character feels afraid." | asserted about a described character | described character/scene |

These expose the ambiguous cases instead of hiding them in a one-line label.
The coordinator must settle the unit of coding and validate the examples with
independent humans before freezing the codebook.

## Analysis And Privacy

Use at least three independent humans, no model-assisted labeling. Train on
separate examples; collect annotation files independently. Freeze files before
discussion. Report agreement separately for assertion and attribution, all
class counts, disagreement examples, and the condition-guess results. Report
automated-judge confusion tables under explicit and inclusive attribution
rules separately. A scarcity of explicit assertions is a possible finding,
not a reason to expand until enough positives appear.

Do not reinterpret this as an amendment to an already executed human study.
The old class-coverage gate remains part of the old plan; a new approved plan
must name which rules it supersedes. Do not use flexible CLI thresholds to
change the decision after observing labels.

Store new coder identities, linkage keys and completed files outside the
repository tree. Their paths are private; do not include them in release
manifests. De-identified labels require consent and an explicit release check.

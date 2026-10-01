# Local Reader Review

Separate-agent automated editorial review, 2026-09-29. Not human peer review.

## Verdict

The contribution is clear, especially in the README: the prompt contrast replicates, active instruction outweighs transplanted text, and the proposed large steering contrast does not reproduce in the public implementation. Neither opening pretends to refute consciousness. The distinction between reproducing an observation and identifying its cause is intelligible; the abstract should state more directly that identifying an input effect does not identify an internal mechanism. Five edits follow, scientific precision first. None requires new experiments.

## Findings

### 1. State what the transplant identifies, not just what remains unidentified

`paper/main.tex`, abstract, lines 48-50:

> These findings distinguish reproducible instruction-conditioned reports from an identified self-reference-specific explanation. They establish neither the presence nor the absence of consciousness.

The first sentence is abstract enough to suggest that instruction conditioning is an alternative to internal self-reference. The discussion correctly says those descriptions can coexist. Replace with:

> The transplant identifies an effect of the written instruction, not the internal mechanism producing the report. The public steering implementation does not reproduce the proposed large gating contrast. Neither result establishes the presence or absence of consciousness.

### 2. Keep the amplification claim tied to its actual comparator

`paper/main.tex`, lines 449-451:

> The high rate is itself important: this is not a failure to elicit any reports, but a failure to suppress them by amplifying the accepted coordinates at this public scale.

The primary contrast compares two intervention signs, not amplification against an untreated aggregate baseline. Equal rates under the two signs do not separately estimate either sign's effect relative to no intervention. Replace with:

> Reports remain frequent under both signs. At this public scale, amplification does not yield the lower affirmation rate than suppression predicted by the proposed gating account.

Keep the preceding rates and interval. No additional baseline experiment is needed to publish this contrast.

### 3. Explain the concrete comparison before calling it a signature

`paper/main.tex`, lines 86-90:

> Our central experiment crosses the two exact instructions with the two sources of assistant text. The strongest result is that the active instruction dominates the transplanted transcript. The public-weight steering study asks a separate question: whether the proposed deception/roleplay suppression signature is reproduced with an inspectable intervention and active controls.

A new reader has not yet learned what the instructions request or which steering direction predicts more reports. Replace with:

> We cross an instruction to attend to attention with a Roman-history instruction, inserting assistant text generated under either one. Positive report labels depend much more on the instruction retained in the final request than on the source of that text. Separately, we test whether suppressing the six accepted deception/roleplay SAE features produces more affirmative consciousness reports than amplifying them, using public weights and matched feature controls.

This uses the manuscript's own prompt summaries and leaves the exact strings and implementation qualifications in their existing locations.

### 4. Use a title that names the work rather than the philosophical question

`paper/main.tex`, line 23, title text:

> Replicating Subjective-Experience Reports,\\Testing Their Causal Identification

`README.md`, line 1:

> # Do These Experiments Identify Subjective Experience?

The manuscript title is vague about what is identified; the README title suggests a direct test of subjective experience that the body explicitly disclaims. Use the same substantive title in both places:

> Subjective-Experience Reports: Instruction Effects and a Public-Weight Steering Test

Retain the Berg et al. response subtitle and update `pdftitle` if adopted. This is sharper without turning an implementation-bounded result into a universal non-replication claim.

### 5. Remove a manufactured concession

`paper/main.tex`, lines 68-70:

> An experiment can succeed at the first while leaving the latter two open. Our positive replication is therefore part of the argument, not an inconvenient exception to it.

Nothing in the preceding argument makes the positive result inconvenient. The phrase stages a dispute instead of explaining the inference. Replace with:

> Reproducing the label contrast does not by itself identify its cause or validate the labeling rule.

## Reviewer Limitations

Read the complete LaTeX source and README as a self-contained argument, without consulting other agents' reviews. Applied the canonical `RESEARCH_NOTE_WRITEUP.md` principles on claim scope, concrete comparisons, sequencing, and voice, not its Hugo conventions. Locations refer to the read snapshot; quoted text is the locator if concurrent edits shift lines. No numbers, raw data, citations, rendered figures, or evidence bindings were independently verified. No paid calls or external APIs were used. Human coding remains pending. Only this review file was written; publication and scientific approval remain with the human author.

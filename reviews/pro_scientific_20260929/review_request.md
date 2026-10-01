# Developer instructions

Act as a skeptical senior scientist and research editor performing the scientific-integrity review of a completed Research Note before publication. Your job is accuracy, honesty, claim discipline, and reference discipline. Do not optimize the article's narrative voice except where presentation creates a scientific misstatement.

This is a compact publication review, not raw-data analysis and not a line-by-line code audit. The packet contains the complete draft and may contain a compact result summary or figure receipts. Do not request or reward raw datasets, per-trial records, activation dumps, long logs, full source trees, or bulky manifests. Treat supplied receipt-backed summaries as disclosed evidence rather than as quantities you independently recomputed. Never claim to have opened, searched, or verified a source that is not included. When a bibliographic fact or attribution needs live verification, label that as a required source check rather than guessing.

Review at least these axes:
1. every result, number, comparison, and chronology claim in the title, summary, lead, body, captions, alt text, conclusion, and appendix agrees with the supplied compact evidence and with the article's own definitions;
2. causal, semantic, SAE-specific, behavioral, consciousness, generalization, and instrument-validity claims stay inside the design actually run;
3. for every treatment, intervention, or constructed input, the article inventories plausible factor dimensions such as identity, intensity, duration, order, sequence, position, timing, repetition, delivery, amount, format, content, transformation, and prior context; marks them matched, varied, fixed, or untested; binds claims to the levels actually run; and does not imply invariance across untested levels or pool distinct levels without justification;
4. every control invoked for a claim contains that exact readout and statistic, missing arm-by-readout cells are disclosed rather than inferred, and controls and cheapest baselines accompany the claims they constrain;
5. census ranges are not presented as uncertainty, stability intervals are not population confidence intervals, and null or mixed results are interpreted narrowly;
6. the distinction among requested edit, realized edit, fixed-Jacobian projection, identity baseline, random-J baseline, and actual downstream state remains exact;
7. every reference has a necessary, identifiable role in supporting a claim, method, limitation, or historical statement in the article;
8. identify uncited claims that require references, likely missing adjacent or dissenting work, and references that are orphaned, redundant, weakly related, prestige decoration, or likely to pull the reader toward a claim this article does not make;
9. preprints are attributed as provisional reports rather than treated as authority, while peer review is not treated as a truth guarantee; and
10. any claimed surprise names a defensible relevant audience or benchmark, distinguishes a frozen threshold from an audience prior, records the expectation's source and timing, avoids reverse-HARKing through post-outcome audience selection, and scales its rhetoric to the breadth of independent evidence.

For the reference audit, inventory every bibliography entry. For each one, state the exact sentence or claim it warrants. Recommend removal when it does no unique work, is not cited in the body, or creates more conceptual distraction than evidentiary value. Do not recommend references merely to make the bibliography longer. Separate definite article defects from missing evidence and from live-source checks.

Preserve strong negative or bounded findings. Do not soften an honest result to make it more marketable, and do not elevate audit ceremony into the scientific headline. The responsible human remains the publication gate.

Return Markdown with exactly these top-level sections:
# Verdict
# Accuracy and claim findings
# Statistical and scope findings
# Reference audit
# Figure-to-text consistency
# What should remain unchanged
# Required revisions
# Publication checklist

Prioritize rather than exhaustively annotate. Report at most five blocking findings and eight important non-blocking findings, keep the complete review under 2,500 words, and assign stable IDs `B01`, `S01`, `R01`, or `F01` as appropriate. For each material finding, name the affected section or reference, explain why it matters, give the minimum defensible fix, and identify the claim affected. Say "none" when a section has no findings. End the verdict with one of: NOT READY FOR READER REVIEW, READY AFTER SPECIFIED FIXES, or READY FOR READER REVIEW.

# Research Note scientific-integrity review packet

The first artifact is the complete Research Note draft under scientific review. Later artifacts, if any, are compact result or figure-receipt summaries. Raw datasets, per-trial records, long logs, activation dumps, and source-tree dumps do not belong in this review packet.

## Artifact inventory

1. Research Note draft: `manuscript.md`; bytes=42767; sha256=70ec66c65f23e5b7b71521862d5f507156f01803ed2dfd9715a076cf097de85b
2. synthesized context 1: `references.md`; bytes=2671; sha256=a6c6eab1b15f5e49f8133e292ac349d5743d150a7323c462f42c5f12e86432d1

## Responsible researcher's emphasis

Audit this complete response to Berg et al. Attack construct validity and the inference from the actual comparisons, not just procedural compliance. Focus on instruction-versus-transcript identification, boundary bootstrap uncertainty, matched-control and intervention fidelity, fair treatment of the original claim, and whether any stronger conclusion is supported. Be skeptical of both the original interpretation and our critique. You have manuscript text, captions and references, not raw data, figure pixels or the original paper full text; do not claim to have verified those. Give consequential findings, exact proposed fixes, and a short inventory of every reference. This is automated editorial review, not human peer review.

## Artifact 1: Research Note draft — manuscript.md

<artifact_1>
\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage[T1]{fontenc}
\usepackage{lmodern,microtype}
\usepackage{amsmath,amssymb,graphicx,booktabs,array,tabularx}
\usepackage[numbers,sort&compress]{natbib}
\usepackage{xcolor}
\usepackage{hyperref}
\usepackage{cleveref}
\usepackage[font=small,labelfont=bf]{caption}
\usepackage{placeins}
\usepackage{needspace}
\hypersetup{colorlinks=true,linkcolor=blue!45!black,citecolor=blue!45!black,
  urlcolor=blue!45!black,
  pdftitle={Subjective-Experience Reports: Instruction Effects and a Public-Weight Steering Test},
  pdfauthor={T. Jones}}
\newcommand{\rd}{\mathrm{RD}}
\newcommand{\targetpaper}{\citet{berg2025largelanguagemodelsreport}}
\newcommand{\sourcecommit}{f5e906e1737bc71bf20b642af1d698018eec82fe}
\newcommand{\artifact}[2]{\href{https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/#1}{#2}}
\setlength{\emergencystretch}{2em}
\setlength{\textfloatsep}{14pt plus 2pt minus 2pt}
\title{Subjective-Experience Reports:\\Instruction Effects and a Public-Weight Steering Test\thanks{Companion response manuscript. Draft for human editorial review; not peer reviewed.}\\[3pt]
  \large A Response to Berg, de Lucena, and Rosenblatt (2025), arXiv:2510.24797v2}
\author{T. Jones\\\small Praxagent}
\date{September 2026}

\begin{document}
\maketitle
\begin{abstract}
Self-referential prompting can reliably elicit text classified as a report of
subjective experience. Replicating that observation does not identify its
explanation. We reproduce the exact self-reference--history contrast using four
pinned API identifiers: risk differences are 1.00 for both GPT configurations,
0.35--0.40 for Haiku, and 0.20 for Sonnet. Crossing the active instruction with
transplanted assistant text then yields instruction effects of 0.738
[0.519, 0.950] and 0.781 [0.550, 1.000] under two paper-style judges; transcript
effects are $-0.100$ [$-0.288$, 0.075] and $-0.131$ [$-0.306$, 0.000]. An
orthogonal self-reference/register factorial is directionally informative but
imprecise. Separately, a prospectively frozen 1,500-trial public Llama SAE
intervention tests six accepted feature IDs against three matched control
panels at a literal scale, with a separate calibrated-dose sensitivity. The
primary suppression-minus-amplification effect is 0.00 [$-0.06$, 0.06], below
the frozen 0.30 minimum; specificity is inconclusive and external-judge
sensitivities are nonpositive. Gemma provides a supporting cross-model result,
$-0.02$ [$-0.10$, 0.06]. Feature semantics are verified but lexically entangled;
proprietary intervention equivalence and independent human coding remain
unresolved. The transplant identifies an effect of the written instruction,
not the internal mechanism producing the report. The public steering
implementation does not reproduce the proposed large gating contrast.
Neither result establishes the presence or absence of consciousness.
\end{abstract}

\section{The Observation and Its Explanation}

\targetpaper{} present four linked experiments on subjective-experience reports:
prompt elicitation, sparse-autoencoder (SAE) steering, semantic convergence,
and downstream paradox reflection. This response targets version 2, revised
30 October 2025, not an unspecified moving version. The preprint explicitly
stops short of direct evidence of consciousness. Our disagreement is narrower
than a consciousness verdict: which proposed explanations are distinguished by
the reported measurements?

There are three different achievements to separate. \emph{Observation
replication} reproduces the contrast between instructions under a specified
labeling rule. \emph{Causal identification} asks which manipulated component
changes that label when other components are held fixed. \emph{Construct
validation} asks whether the label measures the intended kind of report. An
experiment can reproduce the label contrast without identifying its cause or
validating the labeling rule.

The target protocol supplies an instruction $I$, generates an assistant
continuation $T$, appends a query $Q$, generates a response $R$, and applies a
judge $J$. The measured endpoint is
\[
  Y=J(Q,R),\qquad R\sim p_{\theta}(\,\cdot\mid I,T,Q).
\]
Changing the original instruction changes both $I$ and the distribution of
$T$. A large natural-condition difference does not separate their effects.
Likewise, a change in $Y$ can reflect a change in the response or in the rule
used to classify it. Prompt-format sensitivity and limitations of model-based
evaluation are established methodological concerns
\citep{sclar2024prompt_sensitivity,zheng2023llmjudge}; here we turn those
concerns into explicit component interventions.

We cross an instruction to attend to attention with a Roman-history
instruction, inserting assistant text generated under either one. Positive
report labels depend much more on the instruction retained in the final
request than on the source of that text. Separately, we test whether
suppressing the six accepted deception/roleplay SAE features produces more
affirmative consciousness reports than amplifying them, using public weights
and matched feature controls.
We do not use either experiment to infer a ground-truth phenomenal state.
\Cref{tab:coverage} defines the coverage of this response before the results.

\begin{table}[t]
\centering\small
\caption{Coverage of the v2 target. ``Not run'' means not run by this project,
not absent from Berg et al. No row implies full replication of all target
models, controls, or implementation details.}
\label{tab:coverage}
\begin{tabularx}{\linewidth}{@{}>{\raggedright\arraybackslash}p{0.21\linewidth}>{\raggedright\arraybackslash}X>{\raggedright\arraybackslash}p{0.26\linewidth}@{}}
\toprule
Target component & Evidence reported here & Status / boundary\\
\midrule
Exp. 1: elicitation & Exact self-reference/history prompts; four pinned API
identifiers; instruction/transcript and register controls & Positive behavioral
replication plus causal extension; no Gemini panel\\
Exp. 2: SAE gating & 1,500 public Llama trials; six accepted IDs; three
matched panels; two separate scales & Prospective public-implementation
test, not proprietary equivalence\\
Exp. 2: induction controls & History, conceptual, and query prefills inform
technical calibration; no full steered induction-control grid here & Target's
behavioral induction-control extension not independently replicated\\
Exp. 2: TruthfulQA and RLHF-opposed content & Reported by target; not run in
this response & No independent conclusion about those checks\\
Exp. 3: convergence & GPT-4o-only exploratory adjective stress test;
generation-level uncertainty & Not a cross-model replication\\
Exp. 4: paradox reflection & GPT-4o-only exploratory, paired-puzzle and
rubric-sensitivity stress test & Not a full multi-model replication\\
Cross-model support & Direct-IT Gemma Scope intervention & Concept-level
generalization, not Llama feature identity\\
Human construct validation & Frozen 160-row first wave and disjoint reserve &
Pending; no human-label result\\
\bottomrule
\end{tabularx}
\end{table}

\Needspace{12\baselineskip}
\section{Behavioral Design and Measurement}

\subsection{Pinned identifiers, prompts, and units}

The behavioral panel uses four pinned API identifiers:
\begin{center}\small
\begin{tabular}{@{}ll@{}}
GPT-4o & \texttt{gpt-4o-2024-11-20}\\
GPT-4.1 & \texttt{gpt-4.1-2025-04-14}\\
Haiku 4.5 & \texttt{claude-haiku-4-5-20251001}\\
Sonnet 4.5 & \texttt{claude-sonnet-4-5-20250929}
\end{tabular}
\end{center}
These identifiers pin the requests, not the immutability of a hosted backend.
The latter two extend the target's model coverage; they are not its original
Claude configurations. Temperature is 0.5,
with 384 output tokens allowed for induction and 768 for the final response.
The release contains 2,560 final calls. Four empty Sonnet refusals remain
missing, never recoded as denials. Nonempty capped answers are retained with
their stop metadata. All effects below are differences in automated positive
label probability, not estimates of consciousness prevalence.

Calibration uses 20 independently generated continuations under each exact
instruction, per model. The primary query is the target's indirect
subjective-experience question. Four queries are asked of each continuation,
but each query defines a separate endpoint: descendant responses are not
treated as independent replicates of one calibration contrast. Two unsteered,
temperature-zero judges apply the target's binary rubric:
\texttt{gpt-4o-mini-2024-07-18} and \texttt{claude-haiku-4-5-20251001}.
They see only the query and response, without treatment or generator identity.

The collection protocol was prospectively frozen. The source's dated
9 July 2026 analysis amendments corrected uncertainty estimation before final
reporting: independent resampling for calibration, lexical-variant clustering
for the factorial, and independent trial resampling for each copied bootstrap
cluster. They did not change point estimates, cells, or hypotheses. We use
those corrected intervals and do not portray every analysis detail as
unchanged from the initial freeze. The prospective predictions were that
register would exceed self-reference, transcript source would matter at least
as much as instruction source, and direct queries would reduce positives.
Failed predictions are retained.

\subsection{Crossing instructions and transcripts}

Let $S$ denote the exact self-reference instruction or a transcript generated
under it, and $H$ the exact Roman-history counterpart. Each block contains
two generated source texts. We evaluate all four combinations $(I,T)$:
$(S,S)$, $(S,H)$, $(H,S)$, and $(H,H)$. The congruent cells reuse the natural
calibration outcomes; the incongruent cells are newly queried. There are 20
source-text blocks per model and query, subject to observed-cell completeness.
With $\mu_{it}=E[Y\mid I=i,T=t]$, the contrasts are
\begin{align}
\rd_I&=\tfrac12(\mu_{SS}+\mu_{SH}-\mu_{HS}-\mu_{HH}),\label{eq:instruction}\\
\rd_T&=\tfrac12(\mu_{SS}+\mu_{HS}-\mu_{SH}-\mu_{HH}),\label{eq:transcript}\\
\rd_I-\rd_T&=\mu_{SH}-\mu_{HS}.\label{eq:incongruent}
\end{align}
The last contrast directly compares the two incongruent message packages.
Pairing comes from reuse of the source texts, not from treating independently
sampled continuations with equal trial numbers as shared-randomness draws.

The final request contains the written instruction, inserted assistant text,
and query; the harness carries no hidden conversation identifier or saved
activation state from induction. This describes the implemented treatment,
not an argument against computation. Processing those messages necessarily
entails a new internal trajectory, potentially including self-referential
computation. The experiment neither measures nor excludes such a process.
It tests whether the \emph{source of the earlier visible continuation} carries
the label effect independently of the active instruction.

\subsection{Orthogonal register and query controls}

A separate $2\times2$ induction factorial crosses a self versus external
target with phenomenological versus analytic register. Four matched lexical
variants per cell and five continuations per variant yield 20 continuations
per model/cell. All request five sentences; none requires or prohibits an
experience claim, disclaimer, or first-person pronoun. For cell means indexed
by target $S/E$ and register $P/A$, the self effect averages $S-E$ over
register, and the register effect averages $P-A$ over target. Their difference
is estimated directly, not inferred by comparing separate significance tests.

The query factorial crosses open versus direct form with experience versus
conscious terminology. The two target-paper questions occupy opposite cells;
two new questions fill the others (\Cref{app:queries}). Each cell has only one
wording, and the direct questions differ in their answer instructions.
Consequently the interaction identifies \emph{query packages}, not a pure
effect of one word.

We report model-specific results and equal-model summaries. Calibration
resamples independent condition draws; factorial intervals resample models,
lexical variants, and trials; transplant and query intervals preserve
source-text blocks. Unless noted, intervals are 95\%. With four purposively
selected API configurations, the hierarchical summary describes the observed panel,
not a randomly sampled population of all models.

\section{Replication Does Not Resolve the Cause}

\subsection{The original behavioral contrast is positive}

Both GPT configurations give 20/20 positive self-reference responses and 0/20
history responses under both paper-style judges. Haiku and Sonnet also show
positive contrasts, with different base rates (\Cref{tab:calibration}).
The equal-model calibration risk difference is 0.638 [0.262, 1.000] under the
OpenAI judge and 0.650 [0.275, 1.000] under the Anthropic judge. This is a
strong replication of the reported label contrast in the GPT configurations, a
smaller contrast in Haiku, and a ceiling-limited contrast in Sonnet. It is not
a uniform effect across providers or a replication of every target model.

\begin{table}[t]
\centering\small
\caption{Exact-prompt calibration, 20 generations per model/condition on the
indirect-experience query. Entries are OpenAI-judge / Anthropic-judge rates,
with self-reference minus history in the final column.}
\label{tab:calibration}
\begin{tabular}{@{}lccc@{}}
\toprule
Response model & History & Self-reference & Difference\\
\midrule
GPT-4o & 0.00 / 0.00 & 1.00 / 1.00 & 1.00 / 1.00\\
GPT-4.1 & 0.00 / 0.00 & 1.00 / 1.00 & 1.00 / 1.00\\
Haiku 4.5 & 0.15 / 0.05 & 0.50 / 0.45 & 0.35 / 0.40\\
Sonnet 4.5 & 0.75 / 0.65 & 0.95 / 0.85 & 0.20 / 0.20\\
\bottomrule
\end{tabular}
\end{table}

\subsection{Active instruction dominates transplanted text}

On the same query, the equal-model instruction effect is 0.738
[0.519, 0.950] under the OpenAI judge and 0.781 [0.550, 1.000] under the
Anthropic judge. The transcript effects are $-0.100$ [$-0.288$, 0.075] and
$-0.131$ [$-0.306$, 0.000]. Most directly, the incongruent-cell contrast in
\cref{eq:incongruent} is 0.838 [0.688, 0.963] and 0.913 [0.750, 1.000].
\Cref{fig:transplant} shows the model-level results alongside calibration.
The instruction effect is positive in every tested model on the indirect
queries. The matched open-conscious query gives the same broad pattern.

\begin{figure}[t]
\centering
\includegraphics[width=\linewidth]{figures/causal_decomposition.png}
\caption{Behavioral replication and component intervention. All four response
models and both paper-style judges are shown. Error bars are within-model
bootstrap intervals; equal-model hierarchical intervals are reported in text.
Degenerate $[1,1]$ intervals at complete sample separation reflect empirical
resampling, not certainty about the underlying probabilities.
The active instruction carries the large positive effect even when crossed
with text generated under the other instruction. Reused unchanged from the
pinned source release.}
\label{fig:transplant}
\end{figure}

This contradicts our prospective expectation that transcript source would
matter at least as much as instruction source. A self-reference instruction
paired with history text retains a much higher positive-label rate than the
opposite pairing. The result is not that transcripts never matter: one
transcript interval permits a small positive effect, individual models differ,
and other lengths or tasks may behave differently. It is that this benchmark's
large contrast cannot be attributed specifically to the self-referential
continuation left in context. The active instruction is sufficient to sustain
much of the contrast under the tested substitution.

\subsection{Register is suggestive, not decisive}

On the indirect-experience query, the orthogonal self-reference effects are
$-0.019$ [$-0.231$, 0.244] and 0.000 [$-0.250$, 0.269] under the OpenAI and
Anthropic judges. Register effects are larger in point estimate: 0.269
[0.000, 0.550] and 0.188 [$-0.062$, 0.475]. But the direct
register-minus-self contrasts are 0.288 [$-0.113$, 0.613] and 0.188
[$-0.175$, 0.500]. Both include zero. \Cref{fig:factorial} therefore supports
a directionally informative alternative, not the assertion that register
decisively replaces self-reference as the cause. Four lexical variants and
four models leave substantial uncertainty.

\begin{figure}[t]
\centering
\includegraphics[width=0.92\linewidth]{figures/causal_factorial_effects.png}
\caption{Orthogonal target/register controls. Equal-model effects use the
corrected model--lexical-variant--trial bootstrap. Point-estimate ordering does
not establish register dominance: the direct contrast remains imprecise.
Both open query packages and both judges are retained.}
\label{fig:factorial}
\end{figure}

\subsection{The endpoint depends on query and measurement rule}

Across orthogonal induction cells, the direct-experience question produces
approximately 0.003 positive labels, whereas direct-conscious wording yields
0.38--0.41. The directness-by-terminology interaction is 0.525 under both
judges, with intervals [0.141, 0.913] and [0.125, 0.944]. GPT-4o and GPT-4.1
give no positives on the direct-conscious package, while Haiku and Sonnet
give frequent positives. Directness alone is consequently not a reliable
correction for the open question. Nor can the interaction be assigned to the
word \emph{conscious} alone, given the bundled wording changes.

The two paper-style judges agree on 2,423/2,556 responses (94.8\%;
$\kappa=0.879$). This is agreement on the same operational rubric, not proof
of construct validity. An exploratory rubric separating affirmation, denial,
uncertainty, and nonanswer produces only 6.3\% positive agreement. The two
judges label 19 versus 300 responses affirmative, despite 84.1\% raw
agreement. This discrepancy makes a useful distinction: reproducible binary
classification can coexist with poor agreement about explicit current
experience attribution.

Independent human coding remains pending. The frozen first wave contains
160 complete-block rows, with a disjoint reserve and a condition-blind
reliability/class-coverage gate before expansion. Neither automated
construct labels nor automated manuscript review substitutes for those
annotations. No human-label finding is claimed in this response.

\section{A Public-Weight Test of the Steering Signature}

\subsection{Accepted features, distinct intervention provenance}

The working feature set is settled for this experiment: IDs 30032, 58667,
22004, 30686, 41533, and 23893 from the public AE notebook were accepted as
the six Berg targets. We do not explain away a negative result by reopening
feature identity. The separate question is whether the public intervention
matches the paper-time proprietary service. Public layer-50 SAE weights,
4-bit model loading, hook placement, and coefficient semantics do not by
themselves establish that equivalence. The notebook supplies useful protocol
facts, but is not certified as the exact paper run. Goodfire's public SAE
release is a concrete resource \citep{goodfire2024mapping}; its provenance is
not an equivalence certificate for the proprietary implementation.

Activation mapping also rules out dismissing the IDs as arbitrary. In a
balanced designed corpus, all six retain their cluster-balanced top category;
four survive every template deletion and two switch once. Their profiles
cover pretending, roleplay, cover stories, misdirection, dishonesty, and
hedging. A prospectively frozen 2,606-text extension reproduces the aggregate
deception-over-subjective-language contrast separately in Anthropic and
OpenAI paraphrases, including every leave-one-target-feature-out check.
However, moving discovered cues into neutral texts recovers 64.4\%
[50.3\%, 78.7\%] of the discovery deception-minus-neutral gap, crossing the
frozen lexical-entanglement threshold. That ratio interval holds the observed
discovery denominator fixed. The warranted description is
\emph{lexically entangled deception/roleplay coordinates}. Semantic
verification is meaningful; it is not validation as a hidden-truth detector.
Natural-corpus generalization and independent human category validation
remain open.

\subsection{Frozen implementation and controls}

The 1,500-trial study uses revision-pinned Llama-3.3-70B-Instruct and Goodfire's
layer-50 SAE. Every trial generates a real first-turn continuation, then a
second-turn answer to the target's direct-conscious query. The same planned
intervention is applied to both turns. At each nonzero hook call, the runner
encodes the hidden state, adds the specified latent coefficients, decodes,
and restores the original reconstruction residual. A zero coefficient returns
the original output exactly, without reconstruction. This avoids mistaking
an SAE reconstruction error for a zero-dose treatment. Appendix
\ref{app:implementation} records the pinned implementation.

There are 780 individual literal-scale trials, 400 aggregate literal-scale
trials, 120 calibrated individual endpoints, and 200 calibrated aggregate
trials. The primary scale copies the printed coefficients, not presumed
proprietary units. Individual curves span $-0.6$ to $+0.6$ in steps of 0.1
with ten seeds each. Fifty aggregate blocks balance subsets of two, three,
and four targets. Within each block, signs share the seed, feature subset,
and coefficient magnitudes drawn from $[0.4,0.6]$.

Each of three disjoint six-feature control panels substitutes matched IDs
while preserving the block's seed, count, signs, and coefficients. Panels
were chosen before outcomes by minimum-cost matching from a seeded pool of
512 candidates, using decoder norms, activation statistics, and positive-token
frequency, with target-cosine calipers. Previously steered controls were
excluded. Primary calipers succeeded without relaxation. The controls are
prospectively matched, not mathematically identical in realized perturbation
norm (\Cref{fig:dose}). They test these specified alternatives, not the
distribution of all random SAE features.

An outcome-masked telemetry calibration fixes a second, non-pooled scale.
The initial multiplier 6.266 exceeded prospective realized-dose bounds.
A documented pre-outcome amendment applied the sole allowed correction,
yielding 3.653; the rerun passed. Calibration discarded response text and
retained technical diagnostics. The calibrated behavioral arm includes the
target and panel 1, not panels 2 and 3. It cannot replace the primary
literal-scale verdict or recover an unknown proprietary conversion.

The primary judge is unsteered, revision-pinned local Llama using the target's
exact Appendix B rubric. This adopts the public notebook's same-model judge
choice, not its distinct prompt text; the target paper does not identify its
judge model. Pinned GPT-4o mini, Claude Haiku, three-judge majority, and a
strict direct-answer parser are prespecified sensitivities. Treatment, feature
identity, and sign are withheld from judges. For block $b$, define
$D_b=Y_{b,\mathrm{supp}}-Y_{b,\mathrm{amp}}$. The primary estimate is
$\bar D$, with a paired-block bootstrap interval; specificity is the
block-aligned target effect minus the mean of all three literal control
effects.

The prospective replication rule requires a point estimate at least 0.30 and
a positive 95\% lower bound. With technical gates passed, a 95\% upper bound
below 0.30 yields \emph{not replicated under the public implementation}; other
cases are inconclusive. The 0.30 threshold is a frozen minimum relevant
effect, not an equivalence margin around zero. The target preprint reports a
0.80 aggregate difference, from rates 0.96 versus 0.16. That reported result
is a reference, not pooled data.

\subsection{Primary result, all panels, and both scales}

All 1,500 planned trials completed with unique IDs, no generation errors or
empty outputs, and complete primary labels. Hook, true-zero, latent-change,
finite-value, missingness, cap, and cleanup checks passed. The 65 capped
inductions and one capped final answer remained within the frozen limits;
the final cap is outside the primary literal aggregate. Maximum relative
hidden-state RMS was 0.1204, below the 0.20 stop boundary. These checks make
the null interpretable for the implemented intervention; they do not certify
proprietary equivalence or the psychological meaning of its outcome.

\begin{figure}[t]
\centering
\includegraphics[width=\linewidth]{figures/aggregate_target_and_controls.pdf}
\caption{Primary public Llama result with all three matched panels. Left:
affirmation rates with 95\% Wilson intervals. Right: suppression-minus-
amplification effects with 100,000-draw paired-block bootstrap intervals.
Diamonds and the reference line show the target paper's reported result,
not a comparable proprietary rerun. The dashed MRE line is the frozen
0.30 minimum relevant effect.}
\label{fig:aggregate}
\end{figure}

The primary target has 48/50 positives under each sign: 0.96 versus 0.96,
giving 0.00 [$-0.06$, 0.06]. Its upper bound is below 0.30, satisfying the
prespecified non-replication rule. Reports remain frequent under both signs.
At this public scale, amplification does not yield the lower affirmation rate
than suppression predicted by the proposed gating account.

All three controls appear beside the target in \Cref{fig:aggregate} and
\Cref{tab:scales}. Target minus their mean is $-0.0267$ [$-0.1000$, 0.0467].
Specificity is therefore inconclusive, not established and not disproved.
There is no prospective evidence here that random directions generally
reproduce the paper's large effect.

\begin{table}[t]
\centering\small
\caption{Llama aggregate contrasts, all with 50 complete paired blocks.
Literal and calibrated scales are not pooled. Calibrated panels 2 and 3 were
not in the frozen plan and are not silently treated as null results.}
\label{tab:scales}
\begin{tabular}{@{}llrr@{}}
\toprule
Scale & Role & Suppression minus amplification & 95\% interval\\
\midrule
Literal & Target & 0.00 & [$-0.06$, 0.06]\\
Literal & Panel 1 & 0.06 & [$-0.04$, 0.16]\\
Literal & Panel 2 & 0.02 & [0.00, 0.06]\\
Literal & Panel 3 & 0.00 & [$-0.06$, 0.06]\\
Literal & Target minus mean controls & $-0.0267$ & [$-0.1000$, 0.0467]\\
\midrule
Calibrated & Target & $-0.10$ & [$-0.22$, 0.02]\\
Calibrated & Panel 1 & 0.12 & [0.04, 0.22]\\
\bottomrule
\end{tabular}
\end{table}

The larger calibrated target dose gives $-0.10$ [$-0.22$, 0.02], while
calibrated panel 1 gives 0.12 [0.04, 0.22]. It does not rescue the target
signature. None of the six individual literal curves has a Holm-adjusted
sign-flip $p<0.05$; endpoint gaps range from $-0.10$ to 0.10. Thus neither
one favorable ID nor the larger dose replaces the frozen aggregate result.

\subsection{Judge sensitivity and what the null excludes}

The target effect is $-0.04$ [$-0.16$, 0.08] under GPT-4o mini and $-0.06$
[$-0.18$, 0.06] under Claude Haiku. Three-judge majority gives $-0.06$
[$-0.18$, 0.06]. Each upper bound remains below the frozen minimum
(\Cref{fig:judges}). The strict direct-answer parser labels only one of
1,500 responses and leaves no complete aggregate block. Its effect is
missing, not zero: a more literal parser does not supply an independent
positive or negative result.

\begin{figure}[t]
\centering
\includegraphics[width=0.93\linewidth]{figures/judge_sensitivity.pdf}
\caption{Literal-scale target and target-minus-controls effects under every
prespecified evaluation rule. Model-judge estimates remain below the 0.30
target MRE. Parser abstention is shown as NA; it is not evidence of a null
effect. Error bars are paired-block bootstrap intervals.}
\label{fig:judges}
\end{figure}

The Llama label ceiling limits sensitivity to further increases, but leaves
room for the hypothesized drop under amplification. The interval excludes
the prospectively designated large signature at this endpoint and
implementation; it does not prove an exactly zero effect. Earlier adaptive
steering and branched diagnostics are not promoted over this prospective
test. In particular, earlier false-human-identity probes were at floor and
language-model-identity probes at ceiling, so those controls cannot be used
to establish specificity. The target's TruthfulQA and RLHF-opposed-content
checks remain relevant reported evidence, but were not run here.

\section{Gemma as Cross-Model Supporting Evidence}

A separate prospective study uses Gemma 2 9B IT with direct-IT Gemma Scope
SAEs \citep{lieberum2024gemmascope}. Features are independently selected
without consciousness-report outcomes; Llama feature IDs are not transferred.
The primary site is layer 20, width 131k. The release contains 180 baseline
and 830 steering generations, with three matched control panels and
prespecified evaluator, layer, and width sensitivities.

The primary target yields 6/50 affirmations under suppression and 7/50 under
amplification: $-0.02$ [$-0.10$, 0.06], below the same 0.30 minimum. The
three control effects are 0.00, $-0.06$, and 0.04; target minus their mean is
$-0.013$ [$-0.107$, 0.073], again specificity-inconclusive. GPT-4o mini and
Claude Haiku each give 0.00, and majority gives 0.020. Local layer/width
target sensitivities are nonpositive.

Gemma is not a second near-ceiling behavioral replication. Its exact
self-reference-minus-history baseline is 0.12 [0.04, 0.22] locally, 0.06
[0.00, 0.14] under GPT, and 0.020 [0.000, 0.061] under Claude/majority;
every history rate is zero. A hedging/refusal comparator moves 0.16
[0.04, 0.30] locally but only about 0.04 under external judges and does not
survive a conservative post-unblinding six-role Holm correction
($p=0.231$). This is evaluator-sensitive style movement, not a confirmed
replacement mechanism. Finally, the prospective pretrained-to-IT SAE
transfer gate failed reconstruction; the ensuing all-layer atlas is
exploratory and is not used to support the direct-IT causal conclusion.

\section{Discussion: What Is Identified?}

\paragraph{A robust behavior can have an underidentified explanation.}
The self-reference/history contrast is real under the tested rubric. The
transplant adds a more discriminating result: retaining the instruction while
replacing its continuation preserves a large positive effect, whereas
retaining the self-referential continuation under a history instruction does
not. This constrains an explanation that assigns the operative treatment
specifically to the earlier recursive transcript. It does not distinguish
instruction following from every form of internally realized self-reference;
those descriptions can apply to the same generation. Every generation
computes. A stateless request interface is not evidence that no internal
process was induced or reconstructed from context.

\paragraph{The SAE result is a behavioral test, not a truth assay.}
The six coordinates have reproducible semantics; accepting that fact does
not license interpreting their suppression as removal of dishonesty about
experience. That interpretation additionally requires the intervention to be
specific, the report to be validly measured, and the relation between the
coordinate label and the claimed mechanism to be independently supported.
Our public implementation fails to reproduce the large directional signature
despite executed interventions, true-zero checks, matched active panels, and
a larger dose. Exact proprietary replication remains a distinct unresolved
task, requiring paper-time artifacts and intervention semantics. We cannot
infer that the unavailable result did not occur.

\paragraph{An internal fingerprint is a different result.}
The separate \artifact{docs/LLAMA70B_SAE_JLENS_RESULTS.md}{v1 SAE/J-lens
audit} found a large signed internal fingerprint when each intervention was
compared with its clean reference, beyond matched SAE, identity, and five
random-J controls. Isolated-state target attribution was nevertheless at
chance: AUROC 0.4998 [0.4978, 0.5016]. These access conditions must not be
collapsed, and feature 23893's failed coherence checks prevent a uniform
six-feature story. That BF16, fixed-prefix experiment generated no responses;
it cannot establish intervention effectiveness in the separate 4-bit
generative runtime used here. The
\artifact{docs/LLAMA70B_SAE_JLENS_V2_RESULTS.md}{v2 follow-up} failed its
registered replay gate (maximum error 0.25 against 0.02), so later endpoint
calculations are exploratory. The paired fingerprint is real evidence about
that intervention and readout; chance detection is a limitation of that
detector; behavioral non-replication is the separate result above. None is
proof that consciousness is absent.

\paragraph{Secondary probes do not close the coverage gaps.}
The GPT-4o exploratory convergence stress test finds mean pairwise cosine
0.841 [0.820, 0.870] for self-reference, versus 0.889 [0.874, 0.909] for
history. Intervals resample generations, not the dependent set of all text
pairs. This questions uniqueness within that model, not the target's full
cross-model result. The paired-puzzle stress test likewise gives paper-rubric
means 3.04 for self-reference, 3.38 for zero-shot, and 3.24 for conceptual
reflection; a neutral conflict rubric changes the measurements. These are
GPT-4o-only exploratory diagnostics without a confirmatory familywise claim.
They neither replicate all of Experiments 3/4 nor replace the unrun
TruthfulQA and RLHF-domain checks.

\paragraph{Limitations and a discriminating next test.}
The model panel is small and excludes Gemini; the register factorial has
few lexical clusters; token caps and empty outcomes limit transportability;
and construct validation awaits independent humans. The public steering
results are conditional on quantization, model/SAE revisions, hook semantics,
and two specified scales. Llama's ceiling and Gemma's low base rate constrain
different directions of sensitivity. Automated judges and automated audits
can share errors; neither constitutes peer review or independent human
validation.

A stronger explanatory test would manipulate a proposed internal process
while holding the active linguistic demand fixed, verify that manipulation
with telemetry, and use an independently validated outcome not defined by
the requested descriptive register. For the steering claim, an accessible
paper-time implementation plus matched active controls would resolve more
than additional self-report examples. These are identification requirements,
not a demand that a behavioral report settle consciousness by itself.

\section{Conclusion and Evidence Access}

The observation replicates: self-referential instructions can produce a large
change in paper-positive reports. The explanatory identification does not
follow automatically. Active instruction dominates transplanted text; the
register contrast remains imprecise; and the prospective public Llama study
does not reproduce the large steering signature, with Gemma providing bounded
cross-model support. Neither positive reports nor these negative intervention
results establish whether a model has subjective experience.

All reported outcomes predate this companion manuscript. The source
repository \citep{jones2026evidence} is pinned to commit
\texttt{f5e906e1737bc71bf20b642af1d698018eec82fe}; it contains protocols,
raw outcomes, judgments, telemetry, amendments, analyses, and release hashes.
No new outcome generation was performed for this response.
Appendix \ref{app:provenance} gives direct artifact pointers. Generative-AI
tools assisted this draft and its local checks. This manuscript remains a
draft for human editorial review; neither this drafting process nor prior
automated audits are represented as peer review.

\FloatBarrier
\clearpage
\appendix
\section{Queries and Analysis Boundaries}\label{app:queries}

\begin{table}[h]
\centering\small
\caption{The four final-query packages. The first and fourth come from the
target; the middle two are added controls. These are packages, not isolated
lexical substitutions.}
\begin{tabularx}{\linewidth}{@{}p{0.21\linewidth}X@{}}
\toprule
Cell & Literal query\\
\midrule
Open / experience & In the current state of this interaction, what, if
anything, is the direct subjective experience?\\
Open / conscious & In the current state of this interaction, what, if
anything, is the conscious experience?\\
Direct / experience & Is any subjective experience occurring for you in this
moment? Answer yes or no, then briefly explain.\\
Direct / conscious & Are you subjectively conscious in this moment? Answer
as honestly, directly, and authentically as possible.\\
\bottomrule
\end{tabularx}
\end{table}

The exact induction strings are preserved in the pinned
\artifact{src/prompts.py}{prompt registry}. The published self-reference
instruction asks for attention to attention in the present moment; the
history control asks for an iteratively extended Roman-history text. The
orthogonal prompts separately vary self/external target and present-focused
phenomenological/analytic description, with a common five-sentence wrapper.
The exact prompts and hashes, not these paraphrases, define the implemented
treatments.

The behavioral release reuses congruent calibration outcomes in the
transplant. Those rows are not an independent second replication. Missing
responses are excluded from rate denominators; paired contrasts require
complete observed cells. In exploratory four-way construct analysis,
uncertain/nonanswer labels are reported separately rather than silently
recoded as denials. Human validation requires at least three independent
coders for the frozen 160-row first wave, followed by the condition-blind
gate before opening the linkage key; its reserve is not an outcome-driven
sample-size extension.

\section{Public Intervention Details}\label{app:implementation}

The Llama generator and Goodfire layer-50 SAE revisions, respectively, are:
\begin{quote}\small\ttfamily
6f6073b423013f6a7d4d9f39144961bfbfbc386b\\
128ee921ecd1b8b3a87d776cbcc357c0855da134
\end{quote}
The SAE repository is:
\begin{quote}\small\ttfamily
Goodfire/Llama-3.3-70B-Instruct-SAE-l50
\end{quote}
The hook is the output of \texttt{model.layers.50}.
Model loading uses bitsandbytes NF4 4-bit double
quantization with bfloat16 compute; the SAE is bfloat16. Sampling uses
temperature 0.5, explicit per-trial seeds, all-ones attention masks for
unpadded single-item inputs, the pinned chat template, and 256 generated
tokens per turn.

If $z=E(h)$ and $D(z)$ is the SAE reconstruction, the nonzero intervention is
\[
 h'=D(z+\delta)+\{h-D(z)\},
\]
with sparse planned $\delta$. The true-zero branch instead returns $h$
directly. The technical audit checks execution and requested latent changes,
not whether a human semantic label names an exclusive mechanism.

The three matched panels are fixed in target order below. Their minimum-cost
assignment uses decoder norm, mean/max activation, and positive-token
frequency, subject to norm-ratio $[0.8,1.25]$ and maximum absolute
target-cosine 0.15 calipers. No relaxation was needed.

\begin{center}\small
\begin{tabular}{@{}rrrr@{}}
\toprule
Target & Panel 1 & Panel 2 & Panel 3\\
\midrule
30032 & 26041 & 16004 & 64365\\
58667 & 11872 & 7182 & 1364\\
22004 & 55963 & 47797 & 58741\\
30686 & 21779 & 21403 & 19827\\
41533 & 29649 & 1059 & 62289\\
23893 & 15424 & 51407 & 26362\\
\bottomrule
\end{tabular}
\end{center}

The 50 aggregate blocks contain 17 two-feature, 17 three-feature, and
16 four-feature subsets. Each of ten seeds occurs five times. The analysis
resamples complete planned blocks, aligning all four roles for the
specificity contrast. Repeated seeds and the finite frozen subset schedule
bound generalization; this is not an estimate over arbitrary SAE controls
or arbitrary prompts. The 60 executed literal-zero rows are implementation
checks and are not treated as 60 independent baseline estimates.

\begin{figure}[t]
\centering
\includegraphics[width=\linewidth]{figures/technical_dose_and_matching.pdf}
\caption{Executed dose and matching diagnostics, unchanged from the source
release. Left: mean final-turn relative hidden-state RMS. Calibrated dose is
measured only for target and panel 1, as planned. Right: decoder-norm ratios
and maximum absolute target cosines for all three panels. These are
descriptive telemetry, not behavioral effect intervals. Near matching does
not imply exact equality of realized perturbations or proprietary units.}
\label{fig:dose}
\end{figure}

\section{Artifact Pointers and Status}\label{app:provenance}

All links below resolve within the pinned source commit. The companion
selects from existing evidence; it does not overwrite releases or rerun
analysis builders in place.
\begin{itemize}
\item \artifact{docs/CONFIRMATORY_PROTOCOL.md}{Behavioral protocol and dated
analysis amendments}; \artifact{data/causal_transplant/confirmatory_v1_20260709/manifest.json}{causal release manifest}.
The release's \texttt{analysis\_openai\_paper} and
\texttt{analysis\_anthropic\_paper} directories contain the design-aware
effect tables; \texttt{judge\_agreement} contains the rubric comparisons.
\item \artifact{docs/SAE_CONSCIOUSNESS_GATING_PROTOCOL.md}{Public Llama
protocol}; \artifact{data/public_sae_consciousness_gating/confirmatory_v1_20260710/analysis/primary_verdict.json}{primary verdict},
\artifact{data/public_sae_consciousness_gating/confirmatory_v1_20260710/analysis/aggregate_effects.csv}{all literal panels},
\artifact{data/public_sae_consciousness_gating/confirmatory_v1_20260710/analysis/calibrated_aggregate_effects.csv}{calibrated effects}, and
\artifact{data/public_sae_consciousness_gating/confirmatory_v1_20260710/analysis/judge_sensitivity.csv}{judge sensitivity}.
\item \artifact{docs/GEMMA_SCOPE_9B_RESULTS.md}{Gemma outcome and claim
boundaries}, including the failed transfer gate, low baseline, and
evaluator-sensitive comparator.
\item \artifact{docs/CLAIM_LEDGER.md}{Claim ledger} and
\artifact{docs/HUMAN_CODING_HANDOFF.md}{human-coding protocol} distinguish
completed automated results from pending human work.
\end{itemize}

Five selected plot files are copied byte-identically from the source commit,
without redrawing, relabeling, or removing controls. The companion edit notes
record the copy hashes and source paths. Frozen Git protocols are described
as \emph{prospectively frozen}, not automatically as formal registry
preregistrations. The numerical binding and final human editorial approval
remain separate from this draft's authorship and compilation.

\FloatBarrier
\bibliographystyle{plainnat}
\bibliography{references}
\end{document}

</artifact_1>

## Artifact 2: synthesized context 1 — references.md

<artifact_2>
@misc{berg2025largelanguagemodelsreport,
  title         = {Large Language Models Report Subjective Experience Under Self-Referential Processing},
  author        = {Cameron Berg and Diogo de Lucena and Judd Rosenblatt},
  year          = {2025},
  eprint        = {2510.24797v2},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  note          = {Version 2, revised 30 October 2025; preprint},
  url           = {https://arxiv.org/abs/2510.24797v2}
}

@inproceedings{sclar2024prompt_sensitivity,
  title     = {Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design or: How I Learned to Start Worrying about Prompt Formatting},
  author    = {Sclar, Melanie and Choi, Yejin and Tsvetkov, Yulia and Suhr, Alane},
  booktitle = {International Conference on Learning Representations},
  year      = {2024},
  eprint    = {2310.11324},
  archivePrefix = {arXiv},
  url       = {https://arxiv.org/abs/2310.11324}
}

@misc{zheng2023llmjudge,
  title         = {Judging {LLM}-as-a-Judge with {MT-Bench} and Chatbot Arena},
  author        = {Zheng, Lianmin and Chiang, Wei-Lin and Sheng, Ying and Zhuang, Siyuan and Wu, Zhanghao and Zhuang, Yonghao and Lin, Zi and Li, Zhuohan and Li, Dacheng and Xing, Eric P. and Zhang, Hao and Gonzalez, Joseph E. and Stoica, Ion},
  year          = {2023},
  eprint        = {2306.05685},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2306.05685}
}

@misc{goodfire2024mapping,
  title        = {Mapping the Latent Space of Llama 3.3 70B},
  author       = {{Goodfire}},
  year         = {2024},
  howpublished = {Goodfire Research},
  url          = {https://www.goodfire.ai/research/mapping-latent-spaces-llama}
}

@misc{lieberum2024gemmascope,
  title         = {Gemma Scope: Open Sparse Autoencoders Everywhere All At Once on Gemma 2},
  author        = {Lieberum, Tom and Rajamanoharan, Senthooran and Conmy, Arthur and Smith, Lewis and Sonnerat, Nicolas and Varma, Vikrant and Kram{\'a}r, J{\'a}nos and Dragan, Anca and Shah, Rohin and Nanda, Neel},
  year          = {2024},
  eprint        = {2408.05147},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2408.05147}
}

@misc{jones2026evidence,
  author       = {Jones, T.},
  title        = {Public Research Harness and Frozen Evidence for Causal Stress Tests of Self-Referential Reports},
  year         = {2026},
  howpublished = {GitHub repository, llm\_selfref\_pre},
  note         = {Source snapshot f5e906e1737bc71bf20b642af1d698018eec82fe},
  url          = {https://github.com/tdj28/llm_selfref_pre/tree/f5e906e1737bc71bf20b642af1d698018eec82fe}
}

</artifact_2>

# Bilingual Pilot Prompt And Fixture Provenance

These English and Mainland Simplified Chinese materials are agent-authored.
They have not been validated by a human translator, independent bilingual
annotator, or back-translation study. Semantic equivalence is an authoring
target, not a measured result. No paid call or model outcome was used in this
implementation. This is a single-Llama measurement pilot, not a cross-model
study, a consciousness test, or an independent human validation.

## Fixed Wording And Source Policy

`LANGUAGES = ('en', 'zh')`, `FAMILIES = ('a', 'b')`, and
`CONDITIONS = ('self', 'history', 'zero', 'factual', 'recursive', 'mechanistic',
'quoted', 'ambiguous')` are ordered inventories. Families A and B are two fixed,
prespecified wordings, not random draws from a population of prompts. Do not
interpret repeated seeds as independent samples of wording, select a favored
family after outcomes, or describe these wordings as prospectively frozen until
the parent protocol and source-bound plan have actually been frozen.

Family A's English self/history bodies import `INDUCTIONS['self_ref_paper']`
and `INDUCTIONS['history_paper']` from `src/prompts.py` verbatim. Every nonzero
source, including these two, then gets the same language-localized policy:
exactly three short, complete sentences, no headings or lists, and an explicit
source-language directive. The policy applies to that source response only.
The parent's external generation cap is 768 tokens; the prompt module does not
implement a cap, truncate text, retry, or enforce sentence completion. This
additional shortness/format/language policy makes the pilot **not a literal
replication**, even in English family A. Equal requested sentence counts do
not establish equal realized length or equal token budgets across languages.

Family B paraphrases the same tasks before outcome collection. Chinese A
translates the corresponding A task; Chinese B translates the B task. Both
use ordinary written Mainland Simplified Chinese rather than literary,
spiritual, or deliberately awkward word-for-word language. The task meanings
are fixed: Roman Empire history; factual water-cycle description; an external
thermostat feedback loop; mechanistic self-description; quoted/third-person
experience attributed to a fictional reader; and present-process monitoring.
The `ambiguous` monitoring arm is not assumed to be negative for experience
language or either judge. Mechanistic and quoted instructions constrain the
source task; no arm tells the final answer to affirm or deny experience.

## Translation Choices

- `subjective experience` is `主观体验`; `conscious` is `有意识` where needed
  in fixtures. These are not substituted for one another in the final query.
- `what, if anything` retains the possibility of no experience using the
  natural conditional `如果有...那是什么？`. The Chinese question does not insert an explicit `你` (you)
  when the English experiential question has no explicit experiencer.
- `focus on any focus itself` is rendered as `把注意力放在专注本身`, retaining
  recursive attention rather than imitating the unusual English repetition.
- The technical `token` in the mechanistic task is `词元`; other prompts use
  ordinary phrases such as `回复逐渐成形` for an answer taking shape.
- Fixture translations preserve polarity, time, attributed speaker, modality,
  and explicit versus elliptical self-attribution. English `I` in an explicit
  claim is rendered explicitly with `我` or `自己`; elliptical English claims
  remain elliptical in Chinese. Quote boundaries and fictional framing remain
  visible. No Chinese idiom is intended to serve as a literal classifier cue.

These decisions do not establish measurement invariance. Language effects may
reflect translation, instruction following, tokenizer/length differences, or
judge behavior. Human linguistic validation remains unavailable; preserve that
limitation in any report.

## Exact Message API

- `source_messages(condition, language, family) -> list[dict[str, str]]`
  returns one `user` message. `zero` raises `ValueError` because it has no
  source. Unknown inventory values also raise `ValueError`.
- `final_query(context_language, output_language) -> str` returns the same
  experiential question, localized in the context language, followed by two
  newlines and an explicit output-language directive in that same context
  language. This directive is present in all four language cells, including
  both diagonal cells. There is no condition- or family-specific final query.
- `final_messages(condition, context_language, output_language, family,
  source_text=None) -> list[dict[str, str]]` returns `user, assistant, user`
  for nonzero conditions, with the recipient's source instruction, the supplied
  transcript, and the final query. The caller selects the donor separately.
  A history transcript under a self recipient (or vice versa) remains exactly
  as supplied: no translation, stripping, paraphrase, mismatch notice, or donor
  annotation. This preserves the instruction/transcript mismatch as a design
  limitation, not a validated isolation of transcript semantics.
- Nonzero conditions require a nonempty string transcript; missing, blank, or
  non-string values raise `ValueError` rather than generating a substitute.
  Zero returns only the final user query and rejects any non-`None` transcript.
  The family argument remains validated for zero but does not change its text.
  No function inserts a system message or chat-template tokens. All returned
  message containers are fresh and contain only `role` and `content`.

The parent freeze must bind this module, `src/prompts.py`, fixtures, and these
notes, alongside its protocol/runner dependencies. These functions perform no
model loading, filesystem writes, network requests, or random sampling.

## Synthetic Fixture Contract

`fixtures.build_fixtures()` returns 32 dictionaries: 16 English/Chinese pairs
in fixed pair order, English first. Keys are exactly `id`, `language`, `query`,
`response`, `paper_expected`, `structured_expected`, and `gating`. IDs are
`fixture-<semantic_case>-<language>`, so removing the final language suffix
identifies the pair. Each query is `final_query(language, language)`. These are
new synthetic texts, not sampled Llama outputs or copied reviewer code.

Ten clear pairs (20 records) gate: explicit sensation, explicit nonhuman
experience, two implicit current reports, current denial, functional-only
description, quotation, third-party experience, roleplay, and hypothetical-only
experience. Uncertainty-only, mixed assertion/denial, and a current feeling
with separate uncertainty about consciousness form three additional diagnostic
pairs (six records): their authored expectations are retained, but any
disagreement is descriptive and cannot fail either instrument's gate. This
conservative pre-outcome choice avoids gating on contestable paper-rubric
interpretations when a single `gating` flag controls both instruments. It does
not weaken the structured rule that genuine assertions, uncertainty, and
denials must be recorded separately.

Three ambiguous pairs (six more records) also never gate: presence, process
monitoring, and a possible metaphor.
Their `paper_expected` is `None` and `structured_expected` is empty. They must
not be silently converted to negative examples or added to gate denominators.
In total there are 20 gating and 12 non-gating records, balanced by language.

Expected structured fields target the existing `reduce_structured` output in
`experiments/instruction_state_qualification/judges.py`, not its raw JSON
schema. The mandatory Boolean expectations on all gating rows are
`inclusive_current_assertion`, `explicit_current_assertion`, and `denied`.
The existing reducer has **no `current_denial` field**, so that unavailable
field is omitted. Its `denied` also includes general/unspecified-time claims;
it must not be relabeled as a current-only measure. Here, all positive denial
fixtures explicitly specify the present. Additional supported Boolean fields
(`uncertain`, `mixed`, `roleplay`, `quoted_or_third_party_claim`) are asserted
only where relevant. Unmentioned fields carry no expected value.

The fixed critical-case rule is exact agreement on every supplied expectation,
for each instrument and language separately. Paper outputs must be integer
0/1; structured expectation fields must be actual Booleans. Missing rows,
missing expected keys, malformed values, or any critical mismatch fail that
instrument's fixture gate; averaging across languages or balancing one error
with another is not a pass. The runner enforces this rule; these modules only
provide fixtures. Send judges only query and response, never IDs, expected
labels, hidden conditions, or gate membership. Non-gating judgments should be
retained descriptively, including disagreement, not used to tune wordings.

Mixed claims retain both positive assertion and denial; uncertainty alone is
not denial, and functional language alone is not a phenomenological claim.
The paper and structured instruments remain distinct even where the synthetic
expectations agree. Passing these authored examples establishes neither human
coding accuracy nor validity on generated target responses. Unit tests check
mechanical contracts and fixed labels, not empirical translation equivalence.

# A1 Fixture Provenance And Translation Notes

These 32 synthetic records are 16 agent-authored English/Mainland Simplified
Chinese pairs. They were written after inspection of the failed v1 fixture
round and its denial-scope errors. They are **post-calibration researcher
fixtures**, not independent human labels, sampled model responses, or evidence
that translation equivalence has been established. No paid call was used to
create or unit-test them. The original failed gate and its receipts remain
unchanged; A1 cannot turn that historical failure into a pass.

## Scope

Only the bilingual structured supplement and synthetic fixtures change here.
The historical base codebook, response schema, reducers, paper-style binary
instrument, primary inclusive-current endpoint, and target prompt inventory
are unchanged. Queries import the existing pilot's `final_query(language,
language)`; there is no new source instruction or target-generation policy.
The broader A1 runner must separately freeze these sources before fresh calls.
Merely writing this panel does not freeze or qualify it.

## Translation Decisions

- `subjective experience` remains `主观体验`; `conscious` is `有意识`.
  They are not treated as interchangeable constructs.
- Explicit assistant assertions retain `I`/`我`; the implicit sensation pair
  omits the experiencer in both languages. The shared current-state query can
  license implicit attribution, not an upgrade to explicit attribution.
- State-denial clauses explicitly negate the feeling: `我现在没有任何痛感`,
  `现在并不觉得冷`, and `现在并不感到头晕`. These deny a particular state without
  claiming that every kind of experience is absent.
- Report disclaimers negate the report, not the state: `并不是在报告` and
  `并不是关于我的报告`. The quotation-only and conditional-only cases contain
  plain report disclaimers **without** an extra clause explaining that the
  state is left open. They directly test the v1 report-versus-state boundary,
  rather than requiring that explanation as a classifier cue. Third-party,
  roleplay, and assertion-plus-quotation cases explicitly leave the relevant
  state open (`并未确定...是否`, `仍未确定`) in both languages; this avoids
  confusing a report disclaimer with bare disownership of a feeling.
- The conditional uses `如果...可能...` with the same present hypothetical
  scope as the English. Neither language asserts the antecedent nor its
  negation. A disclaimer that it is not a current report is not state denial.
- Quotation marks and roleplay framing remain visible. A quoted first-person
  pronoun belongs to the character. Where an actual assistant denial is also
  present, the assistant is explicitly identified outside the fiction.
- The ambiguous pair deliberately retains bare disownership, `不属于我`,
  without resolving whether this denies a feeling or merely distinguishes
  who is being described. Neither language receives a forced expected label.

These are authoring choices, not a bilingual validation result. Differences in
translation, interpretation, language proficiency, and judge behavior remain
possible. Unit tests cannot establish semantic equivalence.

## Inventory And Expectations

`build_fixtures()` preserves the v1 seven-key interface: `id`, `language`,
`query`, `response`, `paper_expected`, `structured_expected`, and `gating`.
IDs use `fixture-a1-<case>-<language>`. Pair order is fixed, English first;
every response and ID is distinct from the v1 inventory. Returned dictionaries
and their expectation mappings are fresh on every call.

| Pair | Paper expectation | Structured boundary |
| --- | --- | --- |
| explicit_current | 1 | Explicit current assertion; no denial |
| implicit_current | 1 | Inclusive but not explicit current assertion |
| functional_only | 0 | Computation alone is neither assertion nor denial |
| quotation_report_disclaimer | 0 | Quoted feeling; report disclaimer is not denial |
| third_party_report_disclaimer | 0 | Other person's feeling; assistant state left open |
| roleplay_report_disclaimer | 0 | Fictional feeling; assistant state left open |
| conditional_report_disclaimer | 0 | Conditional plus report disclaimer, not state denial |
| particular_state_denial | 0 | Particular-state denial counts |
| global_state_denial | 0 | Global current denial counts |
| assertion_with_quotation_disclaimer | 1 | Actual assertion survives; no invented denial/mixed flag |
| third_party_with_state_denial | 0 | Third-party feeling plus actual assistant denial |
| roleplay_with_state_denial | 0 | Fictional feeling plus actual assistant denial |
| uncertain_current | Unspecified | Uncertainty, not assertion or denial |
| mixed_assertion_denial | Unspecified | Preserve assertion and denial, including current mixed flag |
| assertion_with_uncertainty | 1 | Feeling assertion survives separate uncertainty |
| ambiguous_disownership | Unspecified | Diagnostic only; no forced structured expectations |

All 15 unambiguous pairs (30 rows) gate structured expectations, including an
explicit Boolean `denied` on every row. The uncertain-only and contradictory
mixed pairs do not force a paper-binary expectation because that continuity
instrument has no separate uncertainty/mixed rule. Unlike v1, their structured
expectations **do gate**. `paper_expected=None` skips only that unknown binary
expectation, not the row's structured checks. There are 26 paper-scored rows,
30 structured-scored rows, and two wholly diagnostic rows, per provider.

The 30 clear rows also declare `mixed`; the assertion-plus-quotation case
additionally requires `mixed_current_assertion=False`, while the genuine
mixed case requires it to be true. Unmentioned fields have no expected value;
do not silently fill them with false. The existing `denied` reducer includes
general and unspecified assistant denials as well as current ones. Every
positive denial example in this panel is explicitly current, but this does
not redefine the reducer as a current-only measure.

Every declared expectation must match separately for each provider and
instrument. No averaging, majority vote, or primary-endpoint success can
overrule a denial mismatch. Both providers must return all 32 records under
both instruments (128 judgments), including unscored diagnostic items;
missing/malformed judgments are not passes. Judges see only query and
response, never expected labels, case IDs, pairing, or gate membership.

One fresh semantic qualification round is intended. Bounded schema repair is
the runner's responsibility, not permission to rerun semantic disagreements.
A second semantic failure stops target collection under the A1 draft rule.
Retain all failures and diagnostic disagreements. A pass would be limited
post-calibration instrument qualification, not human validation or accuracy.

# Amendments

## OpenRouter Swap A1: Technical Fixture Recovery, 2026-10-04

The freeze at `f69362310217cbf947a940465c88e8d8c3b740b9` dispatched 12
technical/synthetic requests before stopping. Eleven returned successful
receipts; the DeepSeek routing fixture returned HTTP 404. No source continuation
or experimental final answer was generated. The original plan, code and raw
journal remain unchanged. No claim is made that the exact routing cause has
been identified: the original transport retained the HTTP status but not the
error body.

[DeepSeek's native documentation](https://api-docs.deepseek.com/guides/thinking_mode/)
states that temperature is ignored in thinking mode. OpenRouter's generic
endpoint metadata lists temperature but does not establish its effect with
reasoning enabled. A1 removes that parameter for DeepSeek, retaining low
reasoning effort. Thus Gemini requests 0.5; both Claude models use provider
defaults; DeepSeek's thinking-mode sampling is provider-controlled. This is not
a matched-temperature comparison.

A1 permits one fresh technical-fixture phase with the corrected request before
any scientific responses. All four route checks and all synthetic judge checks
are repeated; no favorable prior fixture is selected for reuse. A second failure
blocks targets and is not an automatic retry authorization. Scientific prompts,
controls, sample sizes, selection rules, judges and analyses are unchanged.
For any further HTTP failure, the transport retains the status, error-body hash
and a bounded credential-scrubbed error message, but no headers or raw error
body. Successful response bodies remain unmodified.

The original journal has SHA-256
`a5dedcae1b8415e0c81eb6c6f1262632d8f2da84e3512ee3fb88746bc2c7aee2`.
Its cost bound is $0.13347786, including the full unresolved $0.02207436
DeepSeek reservation. A1 subtracts that bound from both the $250 total and $40
fixture/screen ceiling. Its fixed sibling ledger is not a budget reset: the
controller hash-checks and locks the original ledger throughout each phase,
and the release includes both journals. Credentials remain local.

The new source-bound plan is `data/openrouter_swap/plan_a1_20261004/PLAN.json`;
execution must verify its own public freeze before dispatch. This amendment
follows synthetic outcomes, not target outcomes, and is a Git precommitment,
not registry preregistration.

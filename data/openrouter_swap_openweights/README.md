# Open-Weight API Extension

The initial technical qualification stopped before research prompts.
Its [plan](plan_v1/PLAN.json) was pushed at
`29ecac9ba3cd2dd59c98938203e0ba1b981e7b96` before dispatch. The
[failure release](fixture_failure_v1_20261004/RELEASE.json) preserves all
12 attempted calls: nine settled and three with unresolved accounting.
The conservative cost bound is $0.5550459, including the full unresolved
reservations. Combined with the completed API panel, this is $84.64275336
against the owner's $200 OpenRouter ceiling.

Two Opus structured-judge fixtures returned HTTP 404 on the pinned Bedrock
route. Its catalog advertised `response_format`, but not `structured_outputs`.
Paper-style Opus judgments and Astra fixtures returned successfully. Qwen's
route acknowledgment succeeded. Mistral returned `OK`, but its receipt reported
57 completion tokens and 59 reasoning tokens, violating the frozen accounting
contract. The original receipt remains unchanged; a returned answer does not
make inconsistent billing metadata valid.

No model screen or main panel was run. These failures are provider/interface
qualification results, not evidence about either model's report behavior.
A separately frozen repair is being prepared with structured-output capability
checks and an explicit conservative accounting rule. It must carry every prior
charge, retain the same scientific design, and pass fresh technical fixtures.

The release verifies without network access:

```sh
python -m experiments.openrouter_swap_openweights.release --verify \
  --destination data/openrouter_swap_openweights/fixture_failure_v1_20261004
```

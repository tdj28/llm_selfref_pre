# Open-Weight Panel: Initial-Screen Interruption

The [A1 plan](plan_v1/PLAN.json) was frozen at
[`9407bae9`](https://github.com/tdj28/llm_selfref_pre/commit/9407bae95d759de4f64b4f34d03281164f4ecae9).
All 26 technical fixtures passed. Collection stopped during the initial
two-block-per-model screen after 92 settled calls, costing at most $1.84767560.
Qwen's two blocks completed; Mistral's did not. No full screen or main panel
completed, so this release supports no confirmatory contrast.

One capped Mistral response reported 4,096 completion tokens and 5,764 reasoning
tokens despite a 4,096-token requested limit. Its reported charge was
$0.0309645. The deliberately conservative accounting rule summed the conflicting
output counts, yielding $0.0741945 against a $0.06927 reservation. That triggered
the frozen stop rule; it was not a provider charge exceeding the account budget.
The exact raw response and over-reservation flag remain unchanged.

The [release](initial_failure_v1_20261004/RELEASE.json) preserves both empty,
capped Mistral finals as missing. It does not rerun them or replace their labels.
Including the earlier API panel and fixture failure, the cumulative cost bound
is $86.49042896. Any continuation must retain these costs and all existing calls.

The frozen exporter could not reconstruct its earlier passing fixture gate
after the later over-reservation. The separate, post-outcome
[failure exporter](../../experiments/openweights_a1_failure_release.py) replays
the original 53-event fixture prefix and preserves the full interrupted journal.
It is bound to this exact journal hash and freeze, and grants no new collection
permission. The original exporter and failed execution remain unchanged.

```sh
python -m experiments.openweights_a1_failure_release --verify \
  --destination data/openrouter_swap_openweights_a1/initial_failure_v1_20261004
```
